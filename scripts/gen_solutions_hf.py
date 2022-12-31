#!/usr/bin/env python3

from tqdm import tqdm
from human_eval.data import read_problems
from more_itertools import chunked
import argparse
import torch
import json, os

from transformers import AutoModelForCausalLM, AutoTokenizer, AutoConfig
from transformers import StoppingCriteriaList, StoppingCriteria
from transformers.deepspeed import HfDeepSpeedConfig
import deepspeed

parser = argparse.ArgumentParser()
parser.add_argument("-m", "--model", type=str, default="Salesforce/codegen-350M-mono")
parser.add_argument('--tokenizer', type=str, default=None)
parser.add_argument("-n", "--num", type=int, default=1, help="Number of completions to generate per task")
parser.add_argument("-t", "--temperature", type=float, default=0.0)
parser.add_argument("-p", "--top_p", type=float, default=1.0)
parser.add_argument("-s", "--stop", type=str, default=None)
parser.add_argument("-o", "--output", type=str, default="samples.jsonl")
parser.add_argument("-b", "--batch_size", type=int, default=8)
parser.add_argument("-a", "--alpha", type=float, default=0.4)
parser.add_argument("-k", "--top_k", type=int, default=3)
parser.add_argument('--local_rank', required=False)
args = parser.parse_args()

if args.stop is None:
    args.stop = ["\nif", "\ndef", "\nclass", "\n\n\n"]
else:
    # Eval the argument
    args.stop = eval(args.stop)

local_rank = int(os.getenv("LOCAL_RANK", "0"))
world_size = int(os.getenv("WORLD_SIZE", "1"))
config = AutoConfig.from_pretrained(args.model)
dtype = torch.float16
model_hidden_size = config.hidden_size
train_batch_size = 1 * world_size

ds_config = {
    "fp16": {
        "enabled": dtype == torch.float16,
    },
    "bf16": {
        "enabled": dtype == torch.bfloat16,
    },
    "zero_optimization": {
        "stage": 3,
        "overlap_comm": True,
        "contiguous_gradients": True,
        "reduce_bucket_size": model_hidden_size * model_hidden_size,
        "stage3_prefetch_bucket_size": 0.9 * model_hidden_size * model_hidden_size,
        "stage3_param_persistence_threshold": 0,
    },
    "steps_per_print": 2000,
    "train_batch_size": train_batch_size,
    "train_micro_batch_size_per_gpu": 1,
    "wall_clock_breakdown": False,
}
dschf = HfDeepSpeedConfig(ds_config)

model = AutoModelForCausalLM.from_pretrained(args.model, torch_dtype=torch.float16)
model = model.eval()
tokenizer = AutoTokenizer.from_pretrained(args.tokenizer or args.model)

ds_engine = deepspeed.initialize(model=model, config_params=ds_config)[0]
ds_engine.module.eval()
model = ds_engine.module

# Stopping criteria for generation using the StoppingCriteria class
class StopSequences(StoppingCriteria):
    def __init__(self, stop_sequences, batch_size):
        StoppingCriteria.__init__(self)
        self.stop_sequences = tokenizer.batch_encode_plus(stop_sequences, add_special_tokens=False)['input_ids']
        self.batch_size = batch_size
        self.finished = [False] * batch_size

    def __call__(self, input_ids, scores):
        for stop in self.stop_sequences:
            # Check if the input_ids end with the stop sequence
            for i in range(self.batch_size):
                if self.finished[i]:
                    continue
                if input_ids[i][-len(stop):].tolist() == stop:
                    self.finished[i] = True
        return all(self.finished)

def generate_completions(prompt, n=8):
    enc = tokenizer.batch_encode_plus([prompt], return_tensors='pt').to(torch.cuda.current_device())
    temp = args.temperature if args.temperature > 0 else None
    with torch.no_grad():
        output = model.generate(
            **enc,
            max_new_tokens=512,
            # do_sample=True if temp is not None else False,
            # top_p=args.top_p,
            # temperature=temp,
            penalty_alpha=args.alpha, top_k=args.top_k,
            pad_token_id=tokenizer.eos_token_id,
            num_return_sequences=n,
            stopping_criteria=StoppingCriteriaList([StopSequences(args.stop, n)]),
        )
    # Remove the prompt
    output = output[:, len(enc['input_ids'][0]):]
    # Decode
    completion = tokenizer.batch_decode(output, skip_special_tokens=True)

    # Remove everything after stop sequence(s)
    for stop in args.stop:
        for i in range(len(completion)):
            if stop in completion[i]:
                completion[i] = completion[i][:completion[i].index(stop)]
    return completion

problems = read_problems()

num_samples_per_task = args.num
with open(args.output, "w") as f:
    for task_id in tqdm(problems, position=0):
        prompt = problems[task_id]["prompt"]
        for chunk in tqdm(chunked(range(num_samples_per_task), args.batch_size), position=1, leave=False):
            completions = generate_completions(prompt, n=len(chunk))
            for completion in completions:
                print(json.dumps({
                    "task_id": task_id,
                    "completion": completion,
                }), file=f)
                f.flush()
