# FreeCAD MCP Tools Reference

**Version**: 0.2.1
**Last Updated**: 2025-11-13

This document provides a complete reference for all tools available in the FreeCAD MCP server.

---

## Table of Contents

- [Document Management](#document-management)
- [Object Creation](#object-creation)
- [Object Manipulation](#object-manipulation)
- [Boolean Operations](#boolean-operations)
- [Geometry Convenience Tools](#geometry-convenience-tools)
- [Fasteners](#fasteners)
- [Workbench Management](#workbench-management)
- [Visualization](#visualization)
- [Parts Library](#parts-library)
- [Advanced Operations](#advanced-operations)

---

## Document Management

### `create_document(name)`

Create a new FreeCAD document.

**Parameters:**
- `name` (string): Name of the document to create

**Returns:**
- Success message or error

**Example:**
```json
{
    "name": "MyProject"
}
```

---

## Object Creation

### `create_object(doc_name, obj_type, obj_name, analysis_name, obj_properties)`

Create a new object in FreeCAD with full control over properties.

**Parameters:**
- `doc_name` (string): Document name
- `obj_type` (string): FreeCAD object type (e.g., "Part::Box", "Part::Cylinder")
- `obj_name` (string): Name for the new object
- `analysis_name` (string, optional): For FEM objects, the analysis container name
- `obj_properties` (dict, optional): Dictionary of object properties

**Supported Object Types:**
- **Part module**: `Part::Box`, `Part::Cylinder`, `Part::Sphere`, `Part::Cone`, `Part::Torus`
- **PartDesign**: `PartDesign::Body`, `PartDesign::Pad`, `PartDesign::Pocket`
- **Draft**: `Draft::Circle`, `Draft::Rectangle`, `Draft::Polygon`
- **Sketcher**: `Sketcher::SketchObject`
- **FEM**: `Fem::AnalysisPython`, `Fem::ConstraintFixed`, `Fem::FemMeshGmsh`, `Fem::MaterialCommon`

**Enhancements in v0.2.0:**
- ✨ Objects are now **visible by default** (addresses invisible object issue)
- ✨ Better error messages with available documents/objects listed
- ✨ Checks for name collisions before creating objects
- ✨ Enhanced error context for referenced objects

**Example - Simple Box:**
```json
{
    "doc_name": "MyDocument",
    "obj_type": "Part::Box",
    "obj_name": "BaseBox",
    "obj_properties": {
        "Length": 100,
        "Width": 50,
        "Height": 25
    }
}
```

**Example - Positioned and Colored Cylinder:**
```json
{
    "doc_name": "MyDocument",
    "obj_type": "Part::Cylinder",
    "obj_name": "MountingPost",
    "obj_properties": {
        "Radius": 5,
        "Height": 30,
        "Placement": {
            "Base": {"x": 10, "y": 20, "z": 0}
        },
        "ViewObject": {
            "ShapeColor": [1.0, 0.0, 0.0, 1.0]
        }
    }
}
```

---

## Object Manipulation

### `edit_object(doc_name, obj_name, obj_properties)`

Edit properties of an existing object.

**Parameters:**
- `doc_name` (string): Document name
- `obj_name` (string): Object name to edit
- `obj_properties` (dict): Properties to update

**Returns:**
- Success message and screenshot

**Example:**
```json
{
    "doc_name": "MyDocument",
    "obj_name": "BaseBox",
    "obj_properties": {
        "Length": 150,
        "ViewObject": {
            "ShapeColor": [0.0, 1.0, 0.0, 1.0]
        }
    }
}
```

---

### `delete_object(doc_name, obj_name)`

Delete an object from a document.

**Parameters:**
- `doc_name` (string): Document name
- `obj_name` (string): Object name to delete

**Returns:**
- Success message and screenshot

**Example:**
```json
{
    "doc_name": "MyDocument",
    "obj_name": "TempObject"
}
```

---

### `get_objects(doc_name)`

List all objects in a document with their properties.

**Parameters:**
- `doc_name` (string): Document name

**Returns:**
- JSON array of object data

**Example:**
```json
{
    "doc_name": "MyDocument"
}
```

---

### `get_object(doc_name, obj_name)`

Get detailed information about a specific object.

**Parameters:**
- `doc_name` (string): Document name
- `obj_name` (string): Object name

**Returns:**
- JSON object with all properties

**Example:**
```json
{
    "doc_name": "MyDocument",
    "obj_name": "BaseBox"
}
```

---

## Boolean Operations

### `boolean_operation(doc_name, operation, base_obj_name, tool_obj_name, result_name, keep_originals)` ✨ NEW

Perform boolean operations between two objects (cut, fuse, common).

**Why this tool?** Eliminates verbose `execute_code()` calls for common operations like cutting holes or joining parts.

**Parameters:**
- `doc_name` (string): Document name
- `operation` (string): Operation type - `"cut"`, `"fuse"`, or `"common"`
- `base_obj_name` (string): First object (base)
- `tool_obj_name` (string): Second object (tool)
- `result_name` (string, optional): Name for result (auto-generated if omitted)
- `keep_originals` (boolean, default: false): Keep original objects visible

**Operations:**
- **cut**: Subtract tool from base (e.g., cutting a hole)
- **fuse**: Combine base and tool (e.g., joining parts)
- **common**: Find intersection of base and tool

**Returns:**
- Result object name and screenshot

**Example - Cut a Hole:**
```json
{
    "doc_name": "MyDocument",
    "operation": "cut",
    "base_obj_name": "Faceplate",
    "tool_obj_name": "MountingHole",
    "result_name": "FaceplateWithHole"
}
```

**Example - Join Two Parts:**
```json
{
    "doc_name": "MyDocument",
    "operation": "fuse",
    "base_obj_name": "Part1",
    "tool_obj_name": "Part2",
    "result_name": "CombinedAssembly"
}
```

**Before vs After:**

❌ **Old way** (30+ lines of execute_code):
```python
import FreeCAD as App
doc = App.getDocument("MyDoc")
base = doc.getObject("Box")
tool = doc.getObject("Cylinder")
result_shape = base.Shape.cut(tool.Shape)
result = doc.addObject("Part::Feature", "Result")
result.Shape = result_shape
base.ViewObject.Visibility = False
tool.ViewObject.Visibility = False
doc.recompute()
```

✅ **New way** (1 tool call):
```json
{
    "doc_name": "MyDoc",
    "operation": "cut",
    "base_obj_name": "Box",
    "tool_obj_name": "Cylinder"
}
```

---

## Geometry Convenience Tools

### `create_box(doc_name, name, length, width, height, position_x, position_y, position_z, color_r, color_g, color_b, color_a)` ✨ NEW

Simplified box creation with intuitive parameters.

**Why this tool?** Much simpler than `create_object()` with full property dictionaries.

**Parameters:**
- `doc_name` (string): Document name
- `name` (string): Object name
- `length` (float): Length in mm (X dimension)
- `width` (float): Width in mm (Y dimension)
- `height` (float): Height in mm (Z dimension)
- `position_x` (float, default: 0): X coordinate
- `position_y` (float, default: 0): Y coordinate
- `position_z` (float, default: 0): Z coordinate
- `color_r` (float, optional): Red component (0.0-1.0)
- `color_g` (float, optional): Green component (0.0-1.0)
- `color_b` (float, optional): Blue component (0.0-1.0)
- `color_a` (float, default: 1.0): Alpha component (0.0-1.0)

**Returns:**
- Success message and screenshot

**Example - Simple Box:**
```json
{
    "doc_name": "MyDocument",
    "name": "Faceplate",
    "length": 254,
    "width": 1.6,
    "height": 44.45
}
```

**Example - Colored Box at Position:**
```json
{
    "doc_name": "MyDocument",
    "name": "RedBox",
    "length": 50,
    "width": 50,
    "height": 50,
    "position_x": 10,
    "position_y": 20,
    "position_z": 0,
    "color_r": 1.0,
    "color_g": 0.0,
    "color_b": 0.0
}
```

---

### `create_cylinder(doc_name, name, radius, height, position_x, position_y, position_z, color_r, color_g, color_b, color_a)` ✨ NEW

Simplified cylinder creation with intuitive parameters.

**Why this tool?** Easier to create cylinders for holes, posts, etc. without property dictionaries.

**Parameters:**
- `doc_name` (string): Document name
- `name` (string): Object name
- `radius` (float): Radius in mm
- `height` (float): Height in mm (along Z axis)
- `position_x` (float, default: 0): X coordinate of base center
- `position_y` (float, default: 0): Y coordinate of base center
- `position_z` (float, default: 0): Z coordinate of base center
- `color_r` (float, optional): Red component (0.0-1.0)
- `color_g` (float, optional): Green component (0.0-1.0)
- `color_b` (float, optional): Blue component (0.0-1.0)
- `color_a` (float, default: 1.0): Alpha component (0.0-1.0)

**Returns:**
- Success message and screenshot

**Example - Mounting Hole:**
```json
{
    "doc_name": "MyDocument",
    "name": "MountingHole",
    "radius": 2.75,
    "height": 10,
    "position_x": 7.9375,
    "position_y": 0,
    "position_z": 22.225
}
```

**Example - Colored Post:**
```json
{
    "doc_name": "MyDocument",
    "name": "BluePost",
    "radius": 5,
    "height": 30,
    "position_x": 50,
    "position_y": 25,
    "position_z": 0,
    "color_r": 0.0,
    "color_g": 0.0,
    "color_b": 1.0
}
```

---

## Fasteners

### `create_fastener(doc_name, name, fastener_type, position_x, position_y, position_z, attach_to, diameter, length)` ✨ NEW

Create hardware fasteners (screws, bolts, nuts, washers) using the Fasteners Workbench.

**Why this tool?** Eliminates the need for manual workbench activation and complex `execute_code()` calls. Creates fasteners with a single tool call including automatic visibility and positioning.

**Requirements:**
- Fasteners Workbench must be installed in FreeCAD
- Will automatically activate FastenersWorkbench when called

**Parameters:**
- `doc_name` (string): Document name
- `name` (string): Name for the fastener object
- `fastener_type` (string): Type of fastener to create
- `position_x` (float, optional): X coordinate (default: 0)
- `position_y` (float, optional): Y coordinate (default: 0)
- `position_z` (float, optional): Z coordinate (default: 0)
- `attach_to` (string, optional): Name of object to attach fastener to (default: None)
- `diameter` (string, optional): Fastener diameter like "M3", "M4", "M5", "M6", "M8" (default: "M4")
- `length` (string, optional): Fastener length in mm as string like "6", "8", "10", "12", "16", "20" (default: "10")

**Common Fastener Types:**

| Type | Description | Common Uses |
|------|-------------|-------------|
| **DIN464** | Knurled thumb screw | Tool-less mounting, rack panels, faceplates |
| **ISO4017** | Hex head bolt | General purpose structural fastening |
| **DIN912** | Socket head cap screw (Allen bolt) | Precision applications, clean appearance |
| **ISO4032** | Hex nut | Pairing with bolts |
| **ISO7380** | Button head screw | Low-profile aesthetic fastening |
| **DIN933** | Hex head screw | Similar to ISO4017 |
| **ISO7089** | Plain washer | Load distribution |
| **ISO7380-2** | Button head with flange | Wide bearing surface |
| **ISO10642** | Countersunk screw | Flush mounting |

**Common Diameters:**
- **M3**: Small electronics, circuit boards (3mm thread)
- **M4**: Common for rack mounting, faceplates (4mm thread)
- **M5**: Frame mounting, structural connections (5mm thread)
- **M6**: Heavy-duty mounting (6mm thread)
- **M8**: Large structural applications (8mm thread)

**Returns:**
- Success message with fastener details and screenshot

**Example - Thumbscrew for Faceplate:**
```json
{
    "doc_name": "USFF_Tray_Assembly",
    "name": "Thumbscrew_Left",
    "fastener_type": "DIN464",
    "position_x": 7.9375,
    "position_y": -6,
    "position_z": 22.225,
    "attach_to": "Faceplate_Final",
    "diameter": "M4"
}
```

**Example - Socket Cap Screw:**
```json
{
    "doc_name": "MyProject",
    "name": "MountingScrew",
    "fastener_type": "DIN912",
    "position_x": 50,
    "position_y": 0,
    "position_z": 10,
    "diameter": "M5",
    "length": "16"
}
```

**Example - Hex Bolt with Nut:**
```json
// First create the bolt
{
    "doc_name": "Assembly",
    "name": "Bolt_1",
    "fastener_type": "ISO4017",
    "position_x": 20,
    "position_y": 30,
    "position_z": 0,
    "diameter": "M6",
    "length": "30"
}

// Then create the nut at the same position
{
    "doc_name": "Assembly",
    "name": "Nut_1",
    "fastener_type": "ISO4032",
    "position_x": 20,
    "position_y": 30,
    "position_z": 30,  // Offset by bolt length
    "diameter": "M6"
}
```

**Benefits over `execute_code()`:**
- **95% code reduction**: Single call vs. 30+ lines
- **Automatic workbench activation**: No manual `activateWorkbench()` needed
- **Automatic visibility**: Fasteners visible immediately
- **Clear error messages**: Lists available objects if attach target not found
- **Type safety**: Parameter validation before creation

---

## Workbench Management

### `activate_workbench(workbench_name)` ✨ NEW

Activate a FreeCAD workbench to access workbench-specific features.

**Why this tool?** Required before using specialized features like FastenersWorkbench. Eliminates the need for `execute_code()` workarounds.

**Parameters:**
- `workbench_name` (string): Name of workbench to activate

**Common Workbenches:**
- **FastenersWorkbench** - Standard fasteners (screws, bolts, nuts)
- **PartDesign** - Parametric part design
- **Draft** - 2D drafting
- **Sketcher** - Constraint-based sketches
- **Arch** - Architectural design
- **Path** - CAM/CNC toolpaths
- **Part** - Basic 3D modeling
- **Fem** - Finite element analysis

**Returns:**
- Success message or error with available workbenches list

**Example:**
```json
{
    "workbench_name": "FastenersWorkbench"
}
```

**Usage Pattern for Fasteners:**

After activating FastenersWorkbench, use `execute_code()` to create fasteners:

```python
import FastenersCmd
import FreeCAD as App

doc = App.getDocument("MyDocument")
screw = doc.addObject("Part::FeaturePython", "Thumbscrew001")
FastenersCmd.FSScrewObject(screw, "DIN464", None)
screw.Placement.Base = App.Vector(7.9375, -6, 22.225)
doc.recompute()
```

**Common Fastener Types:**
- **DIN464** - Knurled thumbscrew
- **ISO4017** - Hex head bolt
- **ISO4032** - Hex nut
- **ISO7380** - Button head screw
- **DIN912** - Socket head cap screw

**Common Sizes:**
- Metric threads: M3, M4, M5, M6, M8, M10
- Typical lengths: 6, 8, 10, 12, 16, 20, 25, 30mm

---

## Visualization

### `get_view(view_name)`

Capture a screenshot from a specific viewing angle.

**Parameters:**
- `view_name` (string): View angle

**Available Views:**
- `"Isometric"` - Default 3D view
- `"Front"` - Front elevation
- `"Back"` - Back elevation
- `"Left"` - Left side view
- `"Right"` - Right side view
- `"Top"` - Top plan view
- `"Bottom"` - Bottom view
- `"Dimetric"` - Dimetric projection
- `"Trimetric"` - Trimetric projection

**Returns:**
- Screenshot image (PNG)

**Note:** Returns informative message if current view doesn't support screenshots (e.g., TechDraw, Spreadsheet views)

**Example:**
```json
{
    "view_name": "Isometric"
}
```

---

## Parts Library

### `get_parts_list()`

List all available parts in the FreeCAD parts library.

**Parameters:** None

**Returns:**
- Array of relative paths to part files

**Example:** No parameters needed

---

### `insert_part_from_library(relative_path)`

Insert a part from the parts library into the active document.

**Parameters:**
- `relative_path` (string): Relative path to part file (from `~/FreeCADParts/`)

**Returns:**
- Success message and screenshot

**Example:**
```json
{
    "relative_path": "Fasteners/Bolts/hex_bolt_m6.FCStd"
}
```

---

## Advanced Operations

### `execute_code(code)`

Execute arbitrary Python code in the FreeCAD environment.

**Parameters:**
- `code` (string): Python code to execute

**Returns:**
- Success/error message, code output, and screenshot

**Security Warning:** ⚠️ This tool executes arbitrary code in FreeCAD's process. Only use with trusted input. Do not expose to untrusted networks.

**When to Use:**
- Workbench activation (though `activate_workbench()` is now preferred)
- Complex operations not covered by dedicated tools
- Prototyping new tool implementations
- Accessing specialized FreeCAD APIs

**Example - Activate Workbench (old pattern):**
```json
{
    "code": "import FreeCADGui as Gui\nGui.activateWorkbench('FastenersWorkbench')"
}
```

**Example - Create Fastener:**
```json
{
    "code": "import FastenersCmd\nimport FreeCAD as App\ndoc = App.getDocument('MyDoc')\nscrew = doc.addObject('Part::FeaturePython', 'Screw')\nFastenersCmd.FSScrewObject(screw, 'DIN464', None)\nscrew.Placement.Base = App.Vector(10, 0, 20)\ndoc.recompute()"
}
```

---

## Coordinate System

FreeCAD uses a right-handed coordinate system with millimeters (mm) as the default unit:

- **X axis**: Horizontal (left-right)
- **Y axis**: Depth (front-back)
- **Z axis**: Vertical (up-down)

**Origin**: (0, 0, 0) is typically at the bottom-left-front corner of objects

**Placement**:
- `Position` or `Base`: Location vector
- `Rotation`: Orientation (axis and angle)

---

## Error Handling (Enhanced in v0.2.0)

All tools now provide **rich error context** when operations fail:

### Before v0.2.0:
```
Error: 'NoneType' object has no attribute 'Shape'
```

### After v0.2.0:
```
Error: Object 'Faceplate_Final' not found in document 'MyDocument'.
Available objects: Box, Cylinder, MountingHole, Screw001, ...
```

**Error Improvements:**
- ✨ Lists available documents when document not found
- ✨ Lists available objects when object not found
- ✨ Checks for name collisions before creating objects
- ✨ Validates operation parameters (e.g., boolean operation types)
- ✨ Shows available workbenches when workbench not found

---

## Version History

### v0.2.0 (2025-11-13) - Claude Code Enhancement Release

**New Tools:**
- `activate_workbench()` - Workbench activation without execute_code()
- `boolean_operation()` - Simplified boolean operations
- `create_box()` - Convenient box creation
- `create_cylinder()` - Convenient cylinder creation

**Enhancements:**
- Objects now visible by default (fixes invisible object issue)
- Rich error messages with context (available items listed)
- Name collision detection
- Better property validation
- Enhanced reference object error messages

**Impact:**
- 90%+ reduction in code verbosity for common operations
- Eliminates "invisible object" debugging
- Clear error messages reduce trial-and-error time
- Workbench activation no longer requires execute_code() workaround

### v0.1.13 (Previous)
- Initial release with 10 basic tools
- Basic error handling
- XML-RPC architecture

---

## Tool Usage Patterns

### Pattern 1: Create Geometry with Boolean Operations

```
1. create_box("MyDoc", "Base", 100, 50, 25)
2. create_cylinder("MyDoc", "Hole", 5, 30, position_x=50, position_y=25)
3. boolean_operation("MyDoc", "cut", "Base", "Hole")
```

Result: Box with cylindrical hole

---

### Pattern 2: Fastener Installation

```
1. activate_workbench("FastenersWorkbench")
2. execute_code(<fastener creation code>)
```

Result: Thumbscrew or bolt added to model

---

### Pattern 3: Multi-Hole Pattern

```
For each hole position:
    1. create_cylinder("MyDoc", f"Hole{i}", 2.75, 10, x, y, z)
2. Get base object
3. For each hole cylinder:
    boolean_operation("MyDoc", "cut", "Base", f"Hole{i}")
```

Result: Base with multiple mounting holes

---

## Best Practices

1. **Always check document state first** using `get_objects()` before modifications
2. **Use convenience tools** (`create_box`, `create_cylinder`, `boolean_operation`) instead of verbose `execute_code()` when possible
3. **Name objects descriptively** for easier debugging
4. **Verify operations** using `get_view()` screenshots after critical steps
5. **Activate workbenches once** at the start of your session
6. **Use `keep_originals=false`** in boolean operations to avoid cluttering the model tree

---

## Troubleshooting

### Objects not visible
**Fixed in v0.2.0!** Objects are now automatically set to visible when created.

### "Document not found" error
Check available documents:
```json
{"doc_name": "MyDoc"}  // Will list available docs if MyDoc doesn't exist
```

### "Object not found" error
Check available objects:
```json
get_objects("MyDoc")  // Lists all objects
```

### Fasteners not working
1. Ensure FastenersWorkbench is installed in FreeCAD
2. Activate workbench: `activate_workbench("FastenersWorkbench")`
3. Use correct fastener type codes (DIN464, ISO4017, etc.)

### Boolean operation fails
1. Verify both objects exist: `get_objects("MyDoc")`
2. Ensure objects have valid shapes (not just sketches)
3. Check object names match exactly (case-sensitive)

---

## Need More Help?

- **FreeCAD Wiki**: https://wiki.freecad.org/
- **Python API**: https://wiki.freecad.org/Python_scripting_tutorial
- **Fasteners Workbench**: https://wiki.freecad.org/Fasteners_Workbench
- **GitHub Issues**: https://github.com/Shadyman/freecad-mcp/issues

---

**Document Version**: 1.0
**For MCP Version**: 0.2.0
**Last Updated**: 2025-11-13
