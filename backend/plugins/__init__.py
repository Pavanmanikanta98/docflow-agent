"""Plugin registry — maps document_type strings to plugin instances.

To register a new document type:
1. Create backend/plugins/your_type.py implementing DocumentPlugin
2. Import it here and add it to REGISTRY

That's it. No other file needs to change.
"""

from backend.plugins.base import DocumentPlugin
from backend.plugins.invoice import InvoicePlugin
from backend.plugins.contract import ContractPlugin

# Registry maps document_type string → plugin instance
REGISTRY: dict[str, DocumentPlugin] = {
    "invoice": InvoicePlugin(),
    "contract": ContractPlugin(),
}


def get_plugin(document_type: str) -> DocumentPlugin:
    """
    Look up a plugin by document type.

    Raises:
        ValueError: if document_type is not registered.
    """
    plugin = REGISTRY.get(document_type.lower())
    if plugin is None:
        supported = ", ".join(REGISTRY.keys())
        raise ValueError(
            f"Unknown document type: '{document_type}'. "
            f"Supported types: {supported}"
        )
    return plugin
