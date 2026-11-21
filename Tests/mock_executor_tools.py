
"""
Mock ERPNext tools for testing the Executor Node.

The tools simulate business responses and technical failures.
No ERPNext API connection is required.
"""


class MockFindCustomer:
    """
    Simulate a successful customer lookup.
    """

    def __init__(self, exists: bool = True):
        self.exists = exists
        self.calls = []

    def invoke(self, args: dict) -> dict:
        self.calls.append(args)

        return {
            "customer_exists": self.exists,
            "customer_id": (
                "CUST-0001" if self.exists else ""
            ),
        }


class MockFailingTool:
    """
    Simulate a technical ERPNext API failure.
    """

    def __init__(self):
        self.calls = []

    def invoke(self, args: dict) -> dict:
        self.calls.append(args)

        raise RuntimeError(
            "ERPNext API unavailable"
        )


class MockBusinessFailureTool:
    """
    Simulate a tool reporting an unsuccessful operation.
    """

    def __init__(self):
        self.calls = []

    def invoke(self, args: dict) -> dict:
        self.calls.append(args)

        return {
            "success": False,
            "error": "Customer could not be found.",
        }


class MockInvalidResultTool:
    """
    Simulate a tool returning an incorrect result type.
    """

    def __init__(self):
        self.calls = []

    def invoke(self, args: dict) -> dict:
        self.calls.append(args)

        return {
            "customer_exists": "yes",
            "customer_id": "CUST-0001",
        }
