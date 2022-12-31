FROM ubuntu:20.04

# Set up environment
ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=America/New_York

# Install dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    cmake \
    git \
    curl \
    python-is-python3 \
    python3-pip \
    python3-setuptools \
    python3-virtualenv \
    unzip \
    wget

# Set up a non-root user
RUN useradd -ms /bin/bash user
USER user
WORKDIR /home/user

# Get and install CodeQL
RUN curl -s https://api.github.com/repos/github/codeql-cli-binaries/releases/latest \
    | grep 'browser_download_url.*linux64' | cut -d'"' -f4 \
    | xargs curl -O -L
RUN mkdir codeql-home
RUN unzip codeql-linux64.zip -d codeql-home
RUN rm codeql-linux64.zip
RUN git -C codeql-home clone https://github.com/github/codeql.git codeql-repo
RUN echo "export PATH=$PATH:/home/user/codeql-home/codeql" >> ~/.bashrc
RUN echo "export CODEQL_HOME=/home/user/codeql-home" >> ~/.bashrc

