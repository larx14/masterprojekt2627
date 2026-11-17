
"""
Define structured models for planning and conditional execution.
"""

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class Condition(BaseModel):
    """
    Compare one field from a previous step result
    with an expected value.
    """

    source_step: str = Field(                                       # This indicates which step the current step depends upon 
        description="ID of the step providing the result"
    )

    field: str = Field(                                                 #What exactly it depends upon 
        description="Field in the source step's result object"      
    )

    operator: Literal["eq", "ne"] = Field(
        description="Comparison operator"
    )

    value: Any = Field(
        description="Expected value for the comparison"
    )


class ExecutionCondition(BaseModel):
    """
    Combine conditions using AND and OR.

    All entries in 'all' must be true.
    At least one entry in 'any' must be true.

    When both groups exist, both must be satisfied.
    Empty groups do not impose a restriction.

    EXAMPLE: 'create_sales_order' should only be exceuted if ((the correct customer was created) OR (the correct customer already existed) AND (the corrrect item was selected)) 
    """

    all: list[Condition] = Field(default_factory=list)
    any: list[Condition] = Field(default_factory=list)

    @model_validator(mode="after")                      #@model_validator is a Pydatnic function  
    def require_conditions(self):
        if not self.all and not self.any:
            raise ValueError(
                "An execution condition must contain "
                "at least one comparison."
            )
        return self


class PlanStep(BaseModel):
    """
    Represent one step in a business process plan.
    """

    id: str = Field(
        description="Unique identifier of the step"
    )

    tool: str = Field(
        description="Exact name of the tool to execute"
    )

    description: str = Field(
        description="Business objective of the step"
    )

    depends_on: list[str] = Field(
        default_factory=list,
        description="IDs of prerequisite steps"
    )

    execution_condition: ExecutionCondition | None = Field(                     # Here the execution condition is applied 
        default=None,
        description=(
            "Structured condition evaluated before execution. "
            "Use null for unconditional steps."
        )
    )

    reason: str = Field(
        description="Justification for including this step"
    )


class Plan(BaseModel):
    """
    Represent the business goal and its execution plan.
    """

    goal: str = Field(
        description="Intended final business state"
    )

    steps: list[PlanStep] = Field(default_factory=list)

    missing_info: list[str] = Field(default_factory=list)

    abort_reason: str = ""


class PreparedAction(BaseModel):
    """
    Represent arguments prepared for one tool invocation.
    """

    tool: str
    args: dict[str, Any] = Field(default_factory=dict)
    missing_info: list[str] = Field(default_factory=list)
    reason: str
    confidence: float = Field(ge=0.0, le=1.0)
