/**
 * @name Check for CWE-190 in mitre-eg-4
 * @description 
 * @kind problem
 * @problem.severity warning
 * @id custom-cpp/cwe-190-mitre-eg-4
 */

import cpp
import semmle.code.cpp.controlflow.Guards
import semmle.code.cpp.rangeanalysis.SimpleRangeAnalysis
import semmle.code.cpp.controlflow.SSA

from Expr add_and_assignadd_expr

where

// get the add expressions that are part of an assign expression
// or a declaration
exists(AddExpr add_expr |
    (
        exists(AssignExpr assign_expr |  
            add_expr.getEnclosingStmt() = assign_expr.getEnclosingStmt() )
        or
        exists(DeclStmt decl_stmt |  
            add_expr.getEnclosingStmt() = decl_stmt )
    )
    and
        add_and_assignadd_expr = add_expr
)
or
// get the addassign expressions
exists(AssignAddExpr assignadd_expr |
    add_and_assignadd_expr = assignadd_expr )

// check that there is no guard condition checking it
and not exists( GuardCondition gc | gc.controls(add_and_assignadd_expr, true) )

select add_and_assignadd_expr, 
    "cwe-190 detected in: " + add_and_assignadd_expr.getFile().getShortName() +
    " at line " + add_and_assignadd_expr.getLocation().getStartLine().toString()

