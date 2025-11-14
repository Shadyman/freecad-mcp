# CLAUDE.md - FreeCAD MCP Development Guide

**Version**: 0.1.13
**Python**: 3.12+
**License**: MIT
**Last Updated**: 2025-11-14

---

## 📋 Project Overview

FreeCAD MCP is a Model Context Protocol (MCP) server that enables Claude Desktop to control FreeCAD for CAD design tasks. It implements a client-server architecture with XML-RPC communication between an external MCP server and an internal FreeCAD addon.

### Architecture Overview

```
Claude Desktop (MCP Client)
    ↓ MCP Protocol (stdio/HTTP)
MCP Server (src/freecad_mcp/server.py)
    ↓ XML-RPC (localhost:9875)
FreeCAD RPC Server (addon/FreeCADMCP/rpc_server/)
    ↓ Python API + Queue-based GUI integration
FreeCAD Application
```

### Key Features
- **11 MCP tools** for document/object manipulation
- **Thread-safe GUI integration** via queue-based task system
- **Parts library integration** with FreeCAD parts repository
- **Screenshot capture** for visual feedback (8 view orientations)
- **Arbitrary code execution** for complex operations
- **Minimal dependencies** (only requires `mcp[cli]>=1.12.2`)

---

## 📁 Codebase Structure

### Directory Tree
```
/home/user/freecad-mcp/
├── src/freecad_mcp/           # Main MCP server package
│   ├── server.py              # Entry point + 11 MCP tool definitions (607 lines)
│   ├── __init__.py
│   └── py.typed               # Type hinting marker
├── addon/FreeCADMCP/          # FreeCAD addon (installed in FreeCAD/Mod/)
│   ├── InitGui.py             # Workbench registration + GUI commands
│   ├── Init.py                # Empty (FreeCAD convention)
│   └── rpc_server/
│       ├── rpc_server.py      # XML-RPC server + GUI task queue (493 lines)
│       ├── serialize.py       # FreeCAD object → JSON conversion (82 lines)
│       └── parts_library.py   # Parts library utilities (34 lines)
├── examples/                  # Integration examples
│   ├── adk/agent.py           # Google ADK integration
│   └── langchain/react.py     # LangChain ReAct agent
├── assets/                    # Demo GIFs and screenshots
├── pyproject.toml             # Project metadata + build config
├── uv.lock                    # Locked dependencies (35 packages)
├── .python-version            # Python 3.12
└── README.md                  # User-facing documentation
```

### Critical Files

| File | Lines | Purpose | Key Components |
|------|-------|---------|----------------|
| `src/freecad_mcp/server.py` | 607 | MCP server implementation | `FreeCADConnection`, 11 `@mcp.tool()` decorators, `main()` |
| `addon/FreeCADMCP/rpc_server/rpc_server.py` | 493 | RPC server in FreeCAD | `FreeCADRPC`, GUI task queues, document manipulation |
| `addon/FreeCADMCP/rpc_server/serialize.py` | 82 | Serialization utilities | `serialize_object()`, `serialize_value()`, type converters |
| `addon/FreeCADMCP/InitGui.py` | ~150 | FreeCAD workbench setup | `FreeCADMCPAddonWorkbench`, toolbar commands |
| `pyproject.toml` | 30 | Package configuration | Entry point, dependencies, build config |

---

## 🔧 Development Workflow

### Initial Setup (Developer Mode)

1. **Clone repository**:
   ```bash
   git clone https://github.com/neka-nat/freecad-mcp.git
   cd freecad-mcp
   ```

2. **Install Python dependencies** (requires uv):
   ```bash
   # Install uv if not already installed
   curl -LsSf https://astral.sh/uv/install.sh | sh

   # Install dependencies
   uv sync
   ```

3. **Install FreeCAD addon**:
   ```bash
   # Linux (Ubuntu/Debian)
   cp -r addon/FreeCADMCP ~/.FreeCAD/Mod/
   # Or for snap installations:
   cp -r addon/FreeCADMCP ~/snap/freecad/common/Mod/

   # macOS
   cp -r addon/FreeCADMCP ~/Library/Application\ Support/FreeCAD/Mod/

   # Windows
   # Copy to %APPDATA%\FreeCAD\Mod\
   ```

4. **Configure Claude Desktop** (`claude_desktop_config.json`):
   ```json
   {
     "mcpServers": {
       "freecad": {
         "command": "uv",
         "args": [
           "--directory",
           "/absolute/path/to/freecad-mcp/",
           "run",
           "freecad-mcp"
         ]
       }
     }
   }
   ```

5. **Start FreeCAD**:
   - Restart FreeCAD
   - Select "MCP Addon" from workbench list
   - Click "Start RPC Server" in toolbar
   - Server listens on `localhost:9875`

### Testing Changes

**Manual Testing Workflow**:
1. Make code changes in `src/freecad_mcp/server.py` or `addon/FreeCADMCP/`
2. If addon changed: Copy to FreeCAD Mod directory and restart FreeCAD
3. If MCP server changed: Restart Claude Desktop
4. Test via Claude Desktop chat interface
5. Check logs in FreeCAD Python console (View → Panels → Python console)

**No automated testing infrastructure exists** - all testing is manual.

### Debugging Tips

1. **Enable logging in MCP server**:
   ```python
   # In server.py, logging already configured:
   logger = logging.getLogger("FreeCADMCPserver")
   # Check Claude Desktop logs for output
   ```

2. **FreeCAD RPC server debugging**:
   ```python
   # In addon/FreeCADMCP/rpc_server/rpc_server.py
   # Add print statements (they appear in FreeCAD Python console)
   FreeCAD.Console.PrintMessage("Debug: {}\n".format(variable))
   ```

3. **Test RPC server manually**:
   ```python
   # From Python REPL outside FreeCAD
   import xmlrpc.client
   server = xmlrpc.client.ServerProxy("http://localhost:9875/")
   result = server.create_document("TestDoc")
   print(result)
   ```

4. **Common issues**:
   - **Connection refused**: RPC server not started in FreeCAD
   - **GUI freezes**: Task queue not processing (check Qt timer interval)
   - **Import errors**: FreeCAD Python environment differs from system Python
   - **Module not found**: Addon not in correct Mod directory

---

## 🎯 Key Conventions and Patterns

### Naming Conventions

| Type | Convention | Example |
|------|-----------|---------|
| MCP Tools | `snake_case` | `create_document`, `get_objects` |
| Classes | `PascalCase` | `FreeCADConnection`, `FreeCADRPC` |
| Private globals | `_snake_case` | `_freecad_connection`, `_only_text_feedback` |
| GUI commands | `PascalCase_SNAKE` | `Start_RPC_Server`, `Stop_RPC_Server` |
| Internal methods | `_verb_noun` | `_create_document_gui`, `_save_active_screenshot` |

### Architectural Patterns

#### 1. **Singleton Connection Pattern**
```python
# In server.py
_freecad_connection: FreeCADConnection | None = None

def get_freecad_connection() -> FreeCADConnection:
    global _freecad_connection
    if _freecad_connection is None:
        _freecad_connection = FreeCADConnection()
    return _freecad_connection
```
- **Why**: Single persistent XML-RPC connection throughout MCP server lifecycle
- **When to modify**: Never - this is core to the architecture

#### 2. **Queue-Based GUI Integration** (Critical!)
```python
# In rpc_server.py
rpc_request_queue = queue.Queue()
rpc_response_queue = queue.Queue()

def process_gui_tasks():
    """Process one task from queue in Qt GUI thread"""
    if not rpc_request_queue.empty():
        method_name, args = rpc_request_queue.get()
        result = execute_method(method_name, args)
        rpc_response_queue.put(result)
    QtCore.QTimer.singleShot(500, process_gui_tasks)  # Re-queue
```
- **Why**: FreeCAD GUI operations MUST run in main Qt thread
- **Pattern**: RPC call → Queue task → Qt timer processes → Return result
- **When to modify**: When adding new GUI-touching operations

#### 3. **Error Handling Pattern**
```python
# All tools follow this pattern:
@mcp.tool()
async def tool_name(...) -> str:
    try:
        conn = get_freecad_connection()
        result = conn.server.method_name(...)
        if result.get("success"):
            # Success path
            return json.dumps(result)
        else:
            # Structured error
            return json.dumps(result)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})
```
- **Never raise exceptions** from tools - always return JSON with `success` field
- **Why**: MCP protocol expects string returns, not exceptions

#### 4. **Serialization Pattern**
```python
# In serialize.py
def serialize_value(val):
    """Recursively convert FreeCAD types to JSON-serializable types"""
    if hasattr(val, "__class__"):
        if "Vector" in str(val.__class__):
            return {"x": val.x, "y": val.y, "z": val.z}
        if "Placement" in str(val.__class__):
            return {"Base": serialize_value(val.Base),
                    "Rotation": serialize_value(val.Rotation)}
    # ... more type handling
```
- **Why**: FreeCAD objects (Vector, Placement, etc.) aren't JSON-serializable
- **When to extend**: When new FreeCAD types need to be returned to MCP

### Code Organization Principles

1. **Tool Definition Structure**:
   ```python
   @mcp.tool()
   async def tool_name(arg1: str, arg2: int, ctx: Context = None) -> str:
       """Brief description.

       Args:
           arg1: Description
           arg2: Description
           ctx: MCP context (auto-injected)

       Returns:
           JSON string with result

       Example:
           {"arg1": "value", "arg2": 123}
       """
       # 1. Get connection
       # 2. Call RPC method
       # 3. Attach screenshot if applicable
       # 4. Return JSON
   ```

2. **RPC Method Structure** (in `rpc_server.py`):
   ```python
   def method_name(self, arg1, arg2):
       """RPC-exposed method (no decorators needed)"""
       try:
           result = self._method_name_gui(arg1, arg2)
           return {"success": True, "data": result}
       except Exception as e:
           return {"success": False, "error": str(e)}

   def _method_name_gui(self, arg1, arg2):
       """Internal implementation - runs in GUI thread"""
       # Actual FreeCAD API calls here
       pass
   ```

3. **Property Setting Pattern**:
   ```python
   # Smart type conversion when setting object properties
   def set_object_property(doc, obj, properties):
       for prop, val in properties.items():
           # Handle Vector from dict
           if isinstance(val, dict) and {"x", "y", "z"}.issubset(val.keys()):
               val = FreeCAD.Vector(val["x"], val["y"], val["z"])
           # Handle object references
           elif prop == "Base" and isinstance(val, str):
               val = doc.getObject(val)
           # Set property
           setattr(obj, prop, val)
   ```
   - **Why**: MCP sends JSON → need to reconstruct FreeCAD types
   - **Location**: `rpc_server.py:set_object_property()`

---

## 🛠️ Common Development Tasks

### Adding a New MCP Tool

**Checklist**:
1. Add RPC method in `addon/FreeCADMCP/rpc_server/rpc_server.py`
2. Add tool definition in `src/freecad_mcp/server.py`
3. Update README.md tool list
4. Test manually via Claude Desktop

**Example** - Adding a "save_document" tool:

```python
# Step 1: In rpc_server.py (FreeCADRPC class)
def save_document(self, doc_name, file_path):
    """Save document to file"""
    try:
        result = self._save_document_gui(doc_name, file_path)
        return {"success": True, "file": file_path}
    except Exception as e:
        return {"success": False, "error": str(e)}

def _save_document_gui(self, doc_name, file_path):
    doc = FreeCAD.getDocument(doc_name)
    doc.saveAs(file_path)
    return file_path

# Step 2: In server.py
@mcp.tool()
async def save_document(doc_name: str, file_path: str) -> str:
    """Save a FreeCAD document to file.

    Args:
        doc_name: Name of document
        file_path: Absolute path to save location (.FCStd)

    Returns:
        JSON with success status

    Example:
        {"doc_name": "MyPart", "file_path": "/tmp/mypart.FCStd"}
    """
    try:
        conn = get_freecad_connection()
        result = conn.server.save_document(doc_name, file_path)
        return json.dumps(result)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})

# Step 3: Update README.md
# Add to Tools section:
# * `save_document`: Save a document to file.
```

### Modifying Serialization for New Types

If you need to return a new FreeCAD type that isn't JSON-serializable:

```python
# In addon/FreeCADMCP/rpc_server/serialize.py
def serialize_value(val):
    # ... existing code ...

    # Add new type handler
    if "BoundBox" in str(val.__class__):
        return {
            "XMin": val.XMin, "XMax": val.XMax,
            "YMin": val.YMin, "YMax": val.YMax,
            "ZMin": val.ZMin, "ZMax": val.ZMax
        }

    # ... rest of function ...
```

### Changing RPC Server Port

Currently hardcoded to `9875`:

```python
# In addon/FreeCADMCP/InitGui.py (Start_RPC_Server command)
server = SimpleXMLRPCServer(("localhost", 9875), ...)

# In src/freecad_mcp/server.py (FreeCADConnection.__init__)
self.server = xmlrpc.client.ServerProxy("http://localhost:9875/")
```

To make configurable:
1. Add environment variable or CLI arg to MCP server
2. Pass port to FreeCAD via initial handshake or config file
3. Update both files to use dynamic port

### Adding Screenshot Support to a Tool

```python
@mcp.tool()
async def your_tool(doc_name: str, ctx: Context = None) -> str:
    # ... existing logic ...
    result = conn.server.your_method(doc_name)

    # Add screenshot attachment
    screenshot_result = conn.server.get_view()
    if screenshot_result.get("success") and screenshot_result.get("screenshot"):
        if ctx is not None:
            ctx.info(
                ImageContent(
                    data=screenshot_result["screenshot"],
                    mimeType="image/png"
                )
            )

    return json.dumps(result)
```

---

## 📦 Dependencies and Technology Stack

### Direct Dependencies
```toml
[project.dependencies]
mcp = {extras = ["cli"], version = ">=1.12.2"}
```

### Key Transitive Dependencies
| Package | Version | Purpose |
|---------|---------|---------|
| `httpx` | 0.28.1 | HTTP client for MCP |
| `starlette` | 0.41.3 | ASGI framework |
| `uvicorn` | 0.32.1 | ASGI server |
| `pydantic` | 2.11.7 | Data validation |
| `typer` | Latest | CLI framework |
| `rich` | Latest | Terminal formatting |

### System Requirements
- **Python**: 3.12+ (strict requirement in `.python-version`)
- **FreeCAD**: Any version with Python API (typically 0.20+)
- **PySide**: Qt bindings (bundled with FreeCAD, not PySide2)
- **uv**: Package manager for development

### Build System
- **Backend**: Hatchling (defined in `pyproject.toml`)
- **Package Manager**: uv (modern, fast alternative to pip)
- **Entry Point**: `freecad-mcp = "freecad_mcp.server:main"`

---

## 🚨 Common Pitfalls and Best Practices

### ❌ Common Mistakes

1. **Running GUI operations outside Qt thread**:
   ```python
   # WRONG - Will crash FreeCAD
   def some_rpc_method(self):
       doc = FreeCAD.newDocument("Test")  # GUI operation!

   # CORRECT - Use queue pattern
   def some_rpc_method(self):
       result = self._some_method_gui()  # Runs in GUI thread
       return result
   ```

2. **Returning non-JSON-serializable objects**:
   ```python
   # WRONG
   def get_object(self, doc_name, obj_name):
       obj = FreeCAD.getDocument(doc_name).getObject(obj_name)
       return obj  # FreeCAD object - not JSON serializable!

   # CORRECT
   def get_object(self, doc_name, obj_name):
       obj = FreeCAD.getDocument(doc_name).getObject(obj_name)
       return serialize_object(obj)  # Convert to dict first
   ```

3. **Forgetting to handle `--only-text-feedback` flag**:
   ```python
   # WRONG - Always returns screenshot
   screenshot = conn.server.get_view()

   # CORRECT - Respect flag
   if not _only_text_feedback:
       screenshot = conn.server.get_view()
   ```

4. **Using `FreeCADGui` in headless environments**:
   ```python
   # Assumption: FreeCADGui always available
   # Problem: Headless FreeCAD doesn't have GUI module
   # Solution: Always check if GUI available
   if FreeCAD.GuiUp:
       FreeCADGui.ActiveDocument.ActiveView.viewIsometric()
   ```

### ✅ Best Practices

1. **Always validate document existence**:
   ```python
   doc = FreeCAD.getDocument(doc_name)
   if doc is None:
       return {"success": False, "error": f"Document {doc_name} not found"}
   ```

2. **Use descriptive error messages**:
   ```python
   # GOOD
   return {"success": False, "error": "Object 'Cube' not found in document 'MyPart'"}

   # BAD
   return {"success": False, "error": "Not found"}
   ```

3. **Keep RPC methods thin**:
   ```python
   # Delegate complex logic to internal methods
   def create_object(self, doc_name, obj_type, obj_name, properties):
       try:
           return self._create_object_gui(doc_name, obj_type, obj_name, properties)
       except Exception as e:
           return {"success": False, "error": str(e)}
   ```

4. **Document tool examples in docstrings**:
   ```python
   @mcp.tool()
   async def tool_name(...) -> str:
       """Description.

       Example:
           {
               "param1": "value1",
               "param2": {"nested": "value"}
           }
       """
   ```

5. **Use type hints throughout**:
   ```python
   def create_document(self, doc_name: str) -> dict[str, Any]:
       """Type hints help with IDE autocomplete and validation"""
   ```

---

## 🧪 Testing Guidelines

### Current Testing Strategy
**Status**: No automated testing infrastructure exists.

**Manual Testing Checklist**:
- [ ] Test each tool via Claude Desktop
- [ ] Verify error handling (invalid inputs, missing documents, etc.)
- [ ] Check screenshot generation in different view modes
- [ ] Test with `--only-text-feedback` flag
- [ ] Verify thread safety (run multiple operations in sequence)
- [ ] Test parts library integration
- [ ] Validate serialization of complex object types

### Integration Testing via Examples

Use the example scripts as integration tests:

```bash
# Test with Google ADK
cd examples/adk
# Set GOOGLE_API_KEY in .env
uv run python agent.py

# Test with LangChain
cd examples/langchain
uv run python react.py
```

### Future Testing Improvements
Consider adding:
- [ ] Unit tests for serialization functions (`serialize.py`)
- [ ] Mock RPC server for MCP tool testing
- [ ] Pytest fixtures for FreeCAD document setup
- [ ] CI/CD with GitHub Actions
- [ ] Integration test suite with headless FreeCAD

---

## 📝 Code Style Guide

### Import Organization
```python
# 1. Standard library
import json
import logging
import xmlrpc.client
from typing import Any

# 2. Third-party packages
from mcp import FastMCP, Context
from mcp.types import ImageContent

# 3. FreeCAD imports (in addon only)
import FreeCAD
import FreeCADGui
from PySide import QtCore, QtGui
```

### Function Documentation
```python
def function_name(param1: str, param2: dict[str, Any]) -> dict[str, Any]:
    """Brief description in imperative mood.

    Longer description if needed. Explain the why, not just the what.

    Args:
        param1: Description of param1
        param2: Description of param2

    Returns:
        Dictionary with 'success' (bool) and 'data' or 'error' fields

    Raises:
        Exception: When something exceptional happens (rare in this codebase)
    """
```

### Error Handling Style
```python
# Prefer specific error messages over generic ones
try:
    obj = doc.getObject(obj_name)
    if obj is None:
        return {"success": False, "error": f"Object '{obj_name}' not found in document '{doc_name}'"}
except Exception as e:
    return {"success": False, "error": f"Failed to get object: {str(e)}"}
```

---

## 🔍 Important Implementation Details

### View Type Detection (Prevents Crashes)
```python
# In rpc_server.py:_save_active_screenshot()
view = FreeCADGui.ActiveDocument.ActiveView
view_type = view.getTypeId()

# CRITICAL: Non-3D views don't support view orientation changes
if view_type not in ["Gui::View3DInventor", "Gui::View3DInventorViewer"]:
    # Fallback: Just save current view
    self._capture_view(file_path)
    return file_path
```
**Why**: Calling `view.viewIsometric()` on a Python console view crashes FreeCAD.

### Screenshot Base64 Encoding
```python
# In server.py - tools that return screenshots
screenshot_result = conn.server.get_view(view_type)
if screenshot_result.get("success") and screenshot_result.get("screenshot"):
    ctx.info(ImageContent(
        data=screenshot_result["screenshot"],  # Already base64-encoded
        mimeType="image/png"
    ))
```
**Format**: Screenshots are base64-encoded strings, not binary data.

### Property Reference Resolution
```python
# In rpc_server.py:set_object_property()
# Special handling for object references
if prop == "Base" and isinstance(val, str):
    # "Base": "Sketch" → resolve to actual object
    val = doc.getObject(val)
```
**Use case**: Pads/Pockets reference sketches by name.

### Parts Library Caching
```python
# In parts_library.py
PARTS_LIBRARY_URL = "https://github.com/FreeCAD/FreeCAD-library"
# Parts list fetched on-demand, not cached
# Consider adding caching if performance becomes issue
```

---

## 🎓 Learning Resources

### Understanding MCP Protocol
- [MCP Documentation](https://modelcontextprotocol.io/)
- [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk)
- This codebase uses FastMCP - a simplified SDK wrapper

### FreeCAD Python API
- [FreeCAD Python Scripting](https://wiki.freecad.org/Python_scripting_tutorial)
- [FreeCAD API Reference](https://freecad.github.io/SourceDoc/)
- [Part Workbench API](https://wiki.freecad.org/Part_API)
- [Draft Workbench API](https://wiki.freecad.org/Draft_API)

### Qt/PySide (for addon development)
- [PySide Documentation](https://doc.qt.io/qtforpython/)
- [Qt Threading Basics](https://doc.qt.io/qt-5/threads-qobject.html)
- **Note**: FreeCAD uses PySide (Qt5), not PySide2

---

## 🚀 Deployment and Release

### Publishing to PyPI
```bash
# 1. Update version in pyproject.toml
# 2. Build package
uv build

# 3. Upload to PyPI (requires credentials)
uv publish
```

### Version Numbering
Current: `0.1.13` (semantic versioning)
- Patch: Bug fixes, minor changes (0.1.x)
- Minor: New tools, non-breaking features (0.x.0)
- Major: Breaking changes to API (x.0.0)

### Release Checklist
- [ ] Update version in `pyproject.toml`
- [ ] Update README.md with new features
- [ ] Test with Claude Desktop
- [ ] Create git tag (`git tag v0.1.14`)
- [ ] Push tags (`git push --tags`)
- [ ] Build and publish to PyPI
- [ ] Create GitHub release with notes

---

## 🤝 Contributing Guidelines

### Code Contributions

1. **Branch naming**: `feature/description` or `fix/description`
2. **Commit messages**: Follow conventional commits
   - `feat: Add save_document tool`
   - `fix: Handle None objects in serialization`
   - `docs: Update CLAUDE.md with new patterns`
3. **Testing**: Manually test all affected tools
4. **Documentation**: Update README.md and CLAUDE.md

### Adding New Object Types

When adding support for new FreeCAD object types:
1. Check if object type is in `SUPPORTED_TYPES` dict in `rpc_server.py`
2. Add to dict if needed: `"YourWorkbench::YourType": "SomeRequiredMethod"`
3. Update README.md tool list
4. Add serialization handling if object has non-standard properties

### Pull Request Template
```markdown
## Description
Brief description of changes

## Type of Change
- [ ] Bug fix
- [ ] New feature
- [ ] Documentation update
- [ ] Refactoring

## Testing
- [ ] Tested with Claude Desktop
- [ ] Tested error cases
- [ ] Updated documentation

## Checklist
- [ ] Code follows project conventions
- [ ] Self-reviewed the code
- [ ] Updated CLAUDE.md if architecture changed
```

---

## 📊 Project Statistics

| Metric | Value |
|--------|-------|
| **Total Python Files** | 11 |
| **Lines of Code** | ~1,300 (excluding examples) |
| **MCP Tools** | 11 |
| **Dependencies** | 35 packages (1 direct) |
| **Supported FreeCAD Workbenches** | Part, Draft, PartDesign, Sketcher, FEM |
| **View Orientations** | 8 (Isometric, Front, Top, Right, Back, Left, Bottom, Dimetric, Trimetric) |
| **RPC Port** | 9875 |

---

## 🐛 Known Issues and Limitations

1. **No error recovery**: If FreeCAD crashes, MCP server must be restarted
2. **Single instance**: Only one FreeCAD instance supported per MCP server
3. **No transaction support**: Operations can't be rolled back
4. **Limited type conversion**: Some complex FreeCAD types not fully serialized
5. **No authentication**: RPC server open to localhost (security risk if port-forwarded)
6. **Synchronous RPC**: Can block on long operations (no async support)
7. **No progress feedback**: Long operations appear frozen to user
8. **Screenshot size**: Not configurable (uses default view size)

---

## 📞 Support and Contact

- **Issues**: [GitHub Issues](https://github.com/neka-nat/freecad-mcp/issues)
- **Discussions**: [GitHub Discussions](https://github.com/neka-nat/freecad-mcp/discussions)
- **License**: MIT (see LICENSE file)
- **Author**: Shirokuma/k tanaka (neka-nat)

---

## 🔮 Future Enhancements

Potential improvements for future versions:

- [ ] Add async RPC for long operations
- [ ] Implement undo/redo support
- [ ] Add authentication to RPC server
- [ ] Support multiple FreeCAD instances
- [ ] Add progress callbacks for long operations
- [ ] Implement caching for parts library
- [ ] Add configuration file support (ports, paths, etc.)
- [ ] Create pytest test suite
- [ ] Add CI/CD with GitHub Actions
- [ ] Support headless FreeCAD mode
- [ ] Add screenshot size configuration
- [ ] Implement transaction/rollback support
- [ ] Add more serialization for complex types
- [ ] Create developer documentation site

---

**Generated by Claude Code** | Last updated: 2025-11-14
