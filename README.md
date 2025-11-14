# FreeCAD MCP

**Model Context Protocol integration for AI-driven CAD operations with FreeCAD**

This repository provides a FreeCAD MCP server that allows you to control FreeCAD from Claude Desktop (and other MCP clients). Version 0.2.0 brings major enhancements based on production usage feedback, dramatically reducing code verbosity and improving developer experience.

## 🎉 What's New in v0.2.0

**90%+ reduction in code verbosity for common CAD operations!**

### New Convenience Tools
- ✨ **`activate_workbench()`** - One-line workbench activation (no more execute_code workarounds!)
- ✨ **`boolean_operation()`** - Cut holes, join parts, find intersections in one tool call
- ✨ **`create_box()`** - Simplified box creation with intuitive parameters
- ✨ **`create_cylinder()`** - Easy cylinder creation for holes and posts

### Enhanced Error Handling
- 🔍 **Rich error messages** - See available documents/objects when something's not found
- ✅ **Name collision detection** - Warns if object name already exists
- 📋 **Context in errors** - Lists available items instead of generic Python exceptions

### Visibility Management
- 👁️ **Objects visible by default** - No more debugging invisible objects!
- 🎨 **Automatic ViewObject setup** - Everything just works

### Documentation
- 📖 **[TOOLS_REFERENCE.md](TOOLS_REFERENCE.md)** - Complete API documentation
- 📚 **[COOKBOOK.md](COOKBOOK.md)** - Real-world examples and patterns
- 📝 **[CHANGELOG.md](CHANGELOG.md)** - Detailed version history

### Impact
**Before v0.2.0**: 200+ lines of execute_code() for a faceplate with holes
**After v0.2.0**: 10 tool calls with clear intent

**See [CHANGELOG.md](CHANGELOG.md) for complete details.**

## Demo

### Design a flange

![demo](./assets/freecad_mcp4.gif)

### Design a toy car

![demo](./assets/make_toycar4.gif)

### Design a part from 2D drawing

#### Input 2D drawing

![input](./assets/b9-1.png)

#### Demo

![demo](./assets/from_2ddrawing.gif)

This is the conversation history.
https://claude.ai/share/7b48fd60-68ba-46fb-bb21-2fbb17399b48

## Install addon

FreeCAD Addon directory is
* Windows: `%APPDATA%\FreeCAD\Mod\`
* Mac: `~/Library/Application\ Support/FreeCAD/Mod/`
* Linux:
  * Ubuntu: `~/.FreeCAD/Mod/` or `~/snap/freecad/common/Mod/` (if you install FreeCAD from snap)
  * Debian: `~/.local/share/FreeCAD/Mod`

Please put `addon/FreeCADMCP` directory to the addon directory.

```bash
git clone https://github.com/neka-nat/freecad-mcp.git
cd freecad-mcp
cp -r addon/FreeCADMCP ~/.FreeCAD/Mod/
```

When you install addon, you need to restart FreeCAD.
You can select "MCP Addon" from Workbench list and use it.

![workbench_list](./assets/workbench_list.png)

And you can start RPC server by "Start RPC Server" command in "FreeCAD MCP" toolbar.

![start_rpc_server](./assets/start_rpc_server.png)

## Setting up Claude Desktop

Pre-installation of the [uvx](https://docs.astral.sh/uv/guides/tools/) is required.

And you need to edit Claude Desktop config file, `claude_desktop_config.json`.

For user.

```json
{
  "mcpServers": {
    "freecad": {
      "command": "uvx",
      "args": [
        "freecad-mcp"
      ]
    }
  }
}
```

If you want to save token, you can set `only_text_feedback` to `true` and use only text feedback.

```json
{
  "mcpServers": {
    "freecad": {
      "command": "uvx",
      "args": [
        "freecad-mcp",
        "--only-text-feedback"
      ]
    }
  }
}
```


For developer.
First, you need clone this repository.

```bash
git clone https://github.com/neka-nat/freecad-mcp.git
```

```json
{
  "mcpServers": {
    "freecad": {
      "command": "uv",
      "args": [
        "--directory",
        "/path/to/freecad-mcp/",
        "run",
        "freecad-mcp"
      ]
    }
  }
}
```

## Tools

### Core Tools
* `create_document` - Create a new document in FreeCAD
* `create_object` - Create a new object in FreeCAD _(enhanced in v0.2.0: objects now visible by default!)_
* `edit_object` - Edit an object in FreeCAD
* `delete_object` - Delete an object in FreeCAD
* `get_objects` - Get all objects in a document
* `get_object` - Get an object in a document
* `get_view` - Get a screenshot of the active view

### ✨ New in v0.2.0
* **`activate_workbench`** - Activate FreeCAD workbenches (FastenersWorkbench, PartDesign, etc.)
* **`boolean_operation`** - Perform cut/fuse/common operations between objects
* **`create_box`** - Convenient box creation with simple parameters
* **`create_cylinder`** - Convenient cylinder creation with simple parameters

### Advanced
* `execute_code` - Execute arbitrary Python code in FreeCAD
* `insert_part_from_library` - Insert a part from the [parts library](https://github.com/FreeCAD/FreeCAD-library)
* `get_parts_list` - Get the list of parts in the [parts library](https://github.com/FreeCAD/FreeCAD-library)

**📖 See [TOOLS_REFERENCE.md](TOOLS_REFERENCE.md) for complete documentation with examples.**

## Quick Start Examples

### Create a Box with Hole (v0.2.0 way)

```
1. create_box("MyDoc", "Base", 100, 50, 25)
2. create_cylinder("MyDoc", "Hole", 5, 30, position_x=50, position_y=0, position_z=12.5)
3. boolean_operation("MyDoc", "cut", "Base", "Hole")
```

**That's it!** 3 tool calls instead of 50+ lines of execute_code().

**📚 See [COOKBOOK.md](COOKBOOK.md) for more real-world examples.**

## Troubleshooting

### Objects not visible
**Fixed in v0.2.0!** Objects are now automatically visible when created.

### "Document not found" error
The error message now lists available documents. Check the error for available options.

### Fasteners not working
1. Ensure FastenersWorkbench is installed in FreeCAD
2. Use `activate_workbench("FastenersWorkbench")` before creating fasteners
3. See [COOKBOOK.md](COOKBOOK.md) for fastener examples

### Need more help?
- **Complete API docs**: [TOOLS_REFERENCE.md](TOOLS_REFERENCE.md)
- **Working examples**: [COOKBOOK.md](COOKBOOK.md)
- **Version history**: [CHANGELOG.md](CHANGELOG.md)
- **Issues**: https://github.com/Shadyman/freecad-mcp/issues

## Contributors

<a href="https://github.com/neka-nat/freecad-mcp/graphs/contributors">
  <img src="https://contrib.rocks/image?repo=neka-nat/freecad-mcp" />
</a>

Made with [contrib.rocks](https://contrib.rocks).
