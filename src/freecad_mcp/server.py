import json
import logging
import xmlrpc.client
from contextlib import asynccontextmanager
from typing import AsyncIterator, Dict, Any, Literal

from mcp.server.fastmcp import FastMCP, Context
from mcp.types import TextContent, ImageContent

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("FreeCADMCPserver")


_only_text_feedback = False


class FreeCADConnection:
    def __init__(self, host: str = "localhost", port: int = 9875):
        self.server = xmlrpc.client.ServerProxy(f"http://{host}:{port}", allow_none=True)

    def ping(self) -> bool:
        return self.server.ping()

    def create_document(self, name: str) -> dict[str, Any]:
        return self.server.create_document(name)

    def create_object(self, doc_name: str, obj_data: dict[str, Any]) -> dict[str, Any]:
        return self.server.create_object(doc_name, obj_data)

    def edit_object(self, doc_name: str, obj_name: str, obj_data: dict[str, Any]) -> dict[str, Any]:
        return self.server.edit_object(doc_name, obj_name, obj_data)

    def delete_object(self, doc_name: str, obj_name: str) -> dict[str, Any]:
        return self.server.delete_object(doc_name, obj_name)

    def insert_part_from_library(self, relative_path: str) -> dict[str, Any]:
        return self.server.insert_part_from_library(relative_path)

    def execute_code(self, code: str) -> dict[str, Any]:
        return self.server.execute_code(code)

    def get_active_screenshot(self, view_name: str = "Isometric") -> str | None:
        try:
            # Check if we're in a view that supports screenshots
            result = self.server.execute_code("""
import FreeCAD
import FreeCADGui

if FreeCAD.Gui.ActiveDocument and FreeCAD.Gui.ActiveDocument.ActiveView:
    view_type = type(FreeCAD.Gui.ActiveDocument.ActiveView).__name__
    
    # These view types don't support screenshots
    unsupported_views = ['SpreadsheetGui::SheetView', 'DrawingGui::DrawingView', 'TechDrawGui::MDIViewPage']
    
    if view_type in unsupported_views or not hasattr(FreeCAD.Gui.ActiveDocument.ActiveView, 'saveImage'):
        print("Current view does not support screenshots")
        False
    else:
        print(f"Current view supports screenshots: {view_type}")
        True
else:
    print("No active view")
    False
""")

            # If the view doesn't support screenshots, return None
            if not result.get("success", False) or "Current view does not support screenshots" in result.get("message", ""):
                logger.info("Screenshot unavailable in current view (likely Spreadsheet or TechDraw view)")
                return None

            # Otherwise, try to get the screenshot
            return self.server.get_active_screenshot(view_name)
        except Exception as e:
            # Log the error but return None instead of raising an exception
            logger.error(f"Error getting screenshot: {e}")
            return None

    def get_objects(self, doc_name: str) -> list[dict[str, Any]]:
        return self.server.get_objects(doc_name)

    def get_object(self, doc_name: str, obj_name: str) -> dict[str, Any]:
        return self.server.get_object(doc_name, obj_name)

    def get_parts_list(self) -> list[str]:
        return self.server.get_parts_list()

    def activate_workbench(self, workbench_name: str) -> dict[str, Any]:
        return self.server.activate_workbench(workbench_name)

    def boolean_operation(
        self,
        doc_name: str,
        operation: str,
        base_obj_name: str,
        tool_obj_name: str,
        result_name: str = None,
        keep_originals: bool = False
    ) -> dict[str, Any]:
        return self.server.boolean_operation(
            doc_name, operation, base_obj_name, tool_obj_name, result_name, keep_originals
        )

    def create_box(
        self,
        doc_name: str,
        name: str,
        length: float,
        width: float,
        height: float,
        position: dict[str, float] = None,
        color: list[float] = None
    ) -> dict[str, Any]:
        return self.server.create_box(doc_name, name, length, width, height, position, color)

    def create_cylinder(
        self,
        doc_name: str,
        name: str,
        radius: float,
        height: float,
        position: dict[str, float] = None,
        direction: dict[str, float] = None,
        color: list[float] = None
    ) -> dict[str, Any]:
        return self.server.create_cylinder(doc_name, name, radius, height, position, direction, color)

    def create_fastener(
        self,
        doc_name: str,
        name: str,
        fastener_type: str,
        position: dict[str, float] = None,
        attach_to: str = None,
        diameter: str = "M4",
        length: str = "10"
    ) -> dict[str, Any]:
        return self.server.create_fastener(doc_name, name, fastener_type, position, attach_to, diameter, length)


@asynccontextmanager
async def server_lifespan(server: FastMCP) -> AsyncIterator[Dict[str, Any]]:
    try:
        logger.info("FreeCADMCP server starting up")
        try:
            _ = get_freecad_connection()
            logger.info("Successfully connected to FreeCAD on startup")
        except Exception as e:
            logger.warning(f"Could not connect to FreeCAD on startup: {str(e)}")
            logger.warning(
                "Make sure the FreeCAD addon is running before using FreeCAD resources or tools"
            )
        yield {}
    finally:
        # Clean up the global connection on shutdown
        global _freecad_connection
        if _freecad_connection:
            logger.info("Disconnecting from FreeCAD on shutdown")
            _freecad_connection.disconnect()
            _freecad_connection = None
        logger.info("FreeCADMCP server shut down")


mcp = FastMCP(
    "FreeCADMCP",
    instructions="FreeCAD integration through the Model Context Protocol",
    lifespan=server_lifespan,
)


_freecad_connection: FreeCADConnection | None = None


def get_freecad_connection():
    """Get or create a persistent FreeCAD connection"""
    global _freecad_connection
    if _freecad_connection is None:
        _freecad_connection = FreeCADConnection(host="localhost", port=9875)
        if not _freecad_connection.ping():
            logger.error("Failed to ping FreeCAD")
            _freecad_connection = None
            raise Exception(
                "Failed to connect to FreeCAD. Make sure the FreeCAD addon is running."
            )
    return _freecad_connection


# Helper function to safely add screenshot to response
def add_screenshot_if_available(response, screenshot):
    """Safely add screenshot to response only if it's available"""
    if screenshot is not None and not _only_text_feedback:
        response.append(ImageContent(type="image", data=screenshot, mimeType="image/png"))
    elif not _only_text_feedback:
        # Add an informative message that will be seen by the AI model and user
        response.append(TextContent(
            type="text", 
            text="Note: Visual preview is unavailable in the current view type (such as TechDraw or Spreadsheet). "
                 "Switch to a 3D view to see visual feedback."
        ))
    return response


@mcp.tool()
def create_document(ctx: Context, name: str) -> list[TextContent]:
    """Create a new document in FreeCAD.

    Args:
        name: The name of the document to create.

    Returns:
        A message indicating the success or failure of the document creation.

    Examples:
        If you want to create a document named "MyDocument", you can use the following data.
        ```json
        {
            "name": "MyDocument"
        }
        ```
    """
    freecad = get_freecad_connection()
    try:
        res = freecad.create_document(name)
        if res["success"]:
            return [
                TextContent(type="text", text=f"Document '{res['document_name']}' created successfully")
            ]
        else:
            return [
                TextContent(type="text", text=f"Failed to create document: {res['error']}")
            ]
    except Exception as e:
        logger.error(f"Failed to create document: {str(e)}")
        return [
            TextContent(type="text", text=f"Failed to create document: {str(e)}")
        ]


@mcp.tool()
def create_object(
    ctx: Context,
    doc_name: str,
    obj_type: str,
    obj_name: str,
    analysis_name: str | None = None,
    obj_properties: dict[str, Any] = None,
) -> list[TextContent | ImageContent]:
    """Create a new object in FreeCAD.
    Object type is starts with "Part::" or "Draft::" or "PartDesign::" or "Fem::".

    Args:
        doc_name: The name of the document to create the object in.
        obj_type: The type of the object to create (e.g. 'Part::Box', 'Part::Cylinder', 'Draft::Circle', 'PartDesign::Body', etc.).
        obj_name: The name of the object to create.
        obj_properties: The properties of the object to create.

    Returns:
        A message indicating the success or failure of the object creation and a screenshot of the object.

    Examples:
        If you want to create a cylinder with a height of 30 and a radius of 10, you can use the following data.
        ```json
        {
            "doc_name": "MyCylinder",
            "obj_name": "Cylinder",
            "obj_type": "Part::Cylinder",
            "obj_properties": {
                "Height": 30,
                "Radius": 10,
                "Placement": {
                    "Base": {
                        "x": 10,
                        "y": 10,
                        "z": 0
                    },
                    "Rotation": {
                        "Axis": {
                            "x": 0,
                            "y": 0,
                            "z": 1
                        },
                        "Angle": 45
                    }
                },
                "ViewObject": {
                    "ShapeColor": [0.5, 0.5, 0.5, 1.0]
                }
            }
        }
        ```

        If you want to create a circle with a radius of 10, you can use the following data.
        ```json
        {
            "doc_name": "MyCircle",
            "obj_name": "Circle",
            "obj_type": "Draft::Circle",
        }
        ```

        If you want to create a FEM analysis, you can use the following data.
        ```json
        {
            "doc_name": "MyFEMAnalysis",
            "obj_name": "FemAnalysis",
            "obj_type": "Fem::AnalysisPython",
        }
        ```

        If you want to create a FEM constraint, you can use the following data.
        ```json
        {
            "doc_name": "MyFEMConstraint",
            "obj_name": "FemConstraint",
            "obj_type": "Fem::ConstraintFixed",
            "analysis_name": "MyFEMAnalysis",
            "obj_properties": {
                "References": [
                    {
                        "object_name": "MyObject",
                        "face": "Face1"
                    }
                ]
            }
        }
        ```

        If you want to create a FEM mechanical material, you can use the following data.
        ```json
        {
            "doc_name": "MyFEMAnalysis",
            "obj_name": "FemMechanicalMaterial",
            "obj_type": "Fem::MaterialCommon",
            "analysis_name": "MyFEMAnalysis",
            "obj_properties": {
                "Material": {
                    "Name": "MyMaterial",
                    "Density": "7900 kg/m^3",
                    "YoungModulus": "210 GPa",
                    "PoissonRatio": 0.3
                }
            }
        }
        ```

        If you want to create a FEM mesh, you can use the following data.
        The `Part` property is required.
        ```json
        {
            "doc_name": "MyFEMMesh",
            "obj_name": "FemMesh",
            "obj_type": "Fem::FemMeshGmsh",
            "analysis_name": "MyFEMAnalysis",
            "obj_properties": {
                "Part": "MyObject",
                "ElementSizeMax": 10,
                "ElementSizeMin": 0.1,
                "MeshAlgorithm": 2
            }
        }
        ```
    """
    freecad = get_freecad_connection()
    try:
        obj_data = {"Name": obj_name, "Type": obj_type, "Properties": obj_properties or {}, "Analysis": analysis_name}
        res = freecad.create_object(doc_name, obj_data)
        screenshot = freecad.get_active_screenshot()
        
        if res["success"]:
            response = [
                TextContent(type="text", text=f"Object '{res['object_name']}' created successfully"),
            ]
            return add_screenshot_if_available(response, screenshot)
        else:
            response = [
                TextContent(type="text", text=f"Failed to create object: {res['error']}"),
            ]
            return add_screenshot_if_available(response, screenshot)
    except Exception as e:
        logger.error(f"Failed to create object: {str(e)}")
        return [
            TextContent(type="text", text=f"Failed to create object: {str(e)}")
        ]


@mcp.tool()
def edit_object(
    ctx: Context, doc_name: str, obj_name: str, obj_properties: dict[str, Any]
) -> list[TextContent | ImageContent]:
    """Edit an object in FreeCAD.
    This tool is used when the `create_object` tool cannot handle the object creation.

    Args:
        doc_name: The name of the document to edit the object in.
        obj_name: The name of the object to edit.
        obj_properties: The properties of the object to edit.

    Returns:
        A message indicating the success or failure of the object editing and a screenshot of the object.
    """
    freecad = get_freecad_connection()
    try:
        res = freecad.edit_object(doc_name, obj_name, {"Properties": obj_properties})
        screenshot = freecad.get_active_screenshot()

        if res["success"]:
            response = [
                TextContent(type="text", text=f"Object '{res['object_name']}' edited successfully"),
            ]
            return add_screenshot_if_available(response, screenshot)
        else:
            response = [
                TextContent(type="text", text=f"Failed to edit object: {res['error']}"),
            ]
            return add_screenshot_if_available(response, screenshot)
    except Exception as e:
        logger.error(f"Failed to edit object: {str(e)}")
        return [
            TextContent(type="text", text=f"Failed to edit object: {str(e)}")
        ]


@mcp.tool()
def delete_object(ctx: Context, doc_name: str, obj_name: str) -> list[TextContent | ImageContent]:
    """Delete an object in FreeCAD.

    Args:
        doc_name: The name of the document to delete the object from.
        obj_name: The name of the object to delete.

    Returns:
        A message indicating the success or failure of the object deletion and a screenshot of the object.
    """
    freecad = get_freecad_connection()
    try:
        res = freecad.delete_object(doc_name, obj_name)
        screenshot = freecad.get_active_screenshot()
        
        if res["success"]:
            response = [
                TextContent(type="text", text=f"Object '{res['object_name']}' deleted successfully"),
            ]
            return add_screenshot_if_available(response, screenshot)
        else:
            response = [
                TextContent(type="text", text=f"Failed to delete object: {res['error']}"),
            ]
            return add_screenshot_if_available(response, screenshot)
    except Exception as e:
        logger.error(f"Failed to delete object: {str(e)}")
        return [
            TextContent(type="text", text=f"Failed to delete object: {str(e)}")
        ]


@mcp.tool()
def execute_code(ctx: Context, code: str) -> list[TextContent | ImageContent]:
    """Execute arbitrary Python code in FreeCAD.

    Args:
        code: The Python code to execute.

    Returns:
        A message indicating the success or failure of the code execution, the output of the code execution, and a screenshot of the object.
    """
    freecad = get_freecad_connection()
    try:
        res = freecad.execute_code(code)
        screenshot = freecad.get_active_screenshot()
        
        if res["success"]:
            response = [
                TextContent(type="text", text=f"Code executed successfully: {res['message']}"),
            ]
            return add_screenshot_if_available(response, screenshot)
        else:
            response = [
                TextContent(type="text", text=f"Failed to execute code: {res['error']}"),
            ]
            return add_screenshot_if_available(response, screenshot)
    except Exception as e:
        logger.error(f"Failed to execute code: {str(e)}")
        return [
            TextContent(type="text", text=f"Failed to execute code: {str(e)}")
        ]


@mcp.tool()
def get_view(ctx: Context, view_name: Literal["Isometric", "Front", "Top", "Right", "Back", "Left", "Bottom", "Dimetric", "Trimetric"]) -> list[ImageContent | TextContent]:
    """Get a screenshot of the active view.

    Args:
        view_name: The name of the view to get the screenshot of.
        The following views are available:
        - "Isometric"
        - "Front"
        - "Top"
        - "Right"
        - "Back"
        - "Left"
        - "Bottom"
        - "Dimetric"
        - "Trimetric"

    Returns:
        A screenshot of the active view.
    """
    freecad = get_freecad_connection()
    screenshot = freecad.get_active_screenshot(view_name)
    
    if screenshot is not None:
        return [ImageContent(type="image", data=screenshot, mimeType="image/png")]
    else:
        return [TextContent(type="text", text="Cannot get screenshot in the current view type (such as TechDraw or Spreadsheet)")]


@mcp.tool()
def insert_part_from_library(ctx: Context, relative_path: str) -> list[TextContent | ImageContent]:
    """Insert a part from the parts library addon.

    Args:
        relative_path: The relative path of the part to insert.

    Returns:
        A message indicating the success or failure of the part insertion and a screenshot of the object.
    """
    freecad = get_freecad_connection()
    try:
        res = freecad.insert_part_from_library(relative_path)
        screenshot = freecad.get_active_screenshot()
        
        if res["success"]:
            response = [
                TextContent(type="text", text=f"Part inserted from library: {res['message']}"),
            ]
            return add_screenshot_if_available(response, screenshot)
        else:
            response = [
                TextContent(type="text", text=f"Failed to insert part from library: {res['error']}"),
            ]
            return add_screenshot_if_available(response, screenshot)
    except Exception as e:
        logger.error(f"Failed to insert part from library: {str(e)}")
        return [
            TextContent(type="text", text=f"Failed to insert part from library: {str(e)}")
        ]


@mcp.tool()
def get_objects(ctx: Context, doc_name: str) -> list[dict[str, Any]]:
    """Get all objects in a document.
    You can use this tool to get the objects in a document to see what you can check or edit.

    Args:
        doc_name: The name of the document to get the objects from.

    Returns:
        A list of objects in the document and a screenshot of the document.
    """
    freecad = get_freecad_connection()
    try:
        screenshot = freecad.get_active_screenshot()
        response = [
            TextContent(type="text", text=json.dumps(freecad.get_objects(doc_name))),
        ]
        return add_screenshot_if_available(response, screenshot)
    except Exception as e:
        logger.error(f"Failed to get objects: {str(e)}")
        return [
            TextContent(type="text", text=f"Failed to get objects: {str(e)}")
        ]


@mcp.tool()
def get_object(ctx: Context, doc_name: str, obj_name: str) -> dict[str, Any]:
    """Get an object from a document.
    You can use this tool to get the properties of an object to see what you can check or edit.

    Args:
        doc_name: The name of the document to get the object from.
        obj_name: The name of the object to get.

    Returns:
        The object and a screenshot of the object.
    """
    freecad = get_freecad_connection()
    try:
        screenshot = freecad.get_active_screenshot()
        response = [
            TextContent(type="text", text=json.dumps(freecad.get_object(doc_name, obj_name))),
        ]
        return add_screenshot_if_available(response, screenshot)
    except Exception as e:
        logger.error(f"Failed to get object: {str(e)}")
        return [
            TextContent(type="text", text=f"Failed to get object: {str(e)}")
        ]


@mcp.tool()
def get_parts_list(ctx: Context) -> list[str]:
    """Get the list of parts in the parts library addon.
    """
    freecad = get_freecad_connection()
    parts = freecad.get_parts_list()
    if parts:
        return [
            TextContent(type="text", text=json.dumps(parts))
        ]
    else:
        return [
            TextContent(type="text", text=f"No parts found in the parts library. You must add parts_library addon.")
        ]


@mcp.tool()
def activate_workbench(ctx: Context, workbench_name: str) -> list[TextContent]:
    """Activate a FreeCAD workbench.

    This is required before using workbench-specific features like FastenersWorkbench.
    Once activated, workbench-specific modules and commands become available.

    Args:
        workbench_name: The name of the workbench to activate.
            Common workbenches include:
            - "FastenersWorkbench" - For adding standard fasteners (screws, bolts, nuts)
            - "PartDesign" - For parametric part design
            - "Draft" - For 2D drafting
            - "Sketcher" - For constraint-based 2D sketches
            - "Arch" - For architectural design
            - "Path" - For CAM/CNC toolpaths
            - "Part" - For basic 3D modeling
            - "Fem" - For finite element analysis

    Returns:
        A message indicating the success or failure of workbench activation.

    Examples:
        To use fasteners (screws, bolts, nuts), you must first activate the FastenersWorkbench:
        ```json
        {
            "workbench_name": "FastenersWorkbench"
        }
        ```

        After activation, you can use execute_code() to create fasteners:
        ```python
        import FastenersCmd
        import FreeCAD as App

        doc = App.getDocument("MyDocument")
        screw = doc.addObject("Part::FeaturePython", "Screw")
        FastenersCmd.FSScrewObject(screw, "DIN464", None)  # DIN464 = Thumbscrew
        screw.Placement.Base = App.Vector(10, 0, 20)
        doc.recompute()
        ```
    """
    freecad = get_freecad_connection()
    try:
        res = freecad.activate_workbench(workbench_name)
        if res["success"]:
            return [
                TextContent(
                    type="text",
                    text=f"Workbench '{res['workbench']}' activated successfully. "
                         f"Workbench-specific modules are now available."
                )
            ]
        else:
            return [
                TextContent(type="text", text=f"Failed to activate workbench: {res['error']}")
            ]
    except Exception as e:
        logger.error(f"Failed to activate workbench: {str(e)}")
        return [
            TextContent(type="text", text=f"Failed to activate workbench: {str(e)}")
        ]


@mcp.tool()
def boolean_operation(
    ctx: Context,
    doc_name: str,
    operation: Literal["cut", "fuse", "common"],
    base_obj_name: str,
    tool_obj_name: str,
    result_name: str = None,
    keep_originals: bool = False
) -> list[TextContent | ImageContent]:
    """Perform boolean operation between two objects.

    This tool simplifies common CAD operations like cutting holes, joining parts, or finding intersections.
    Much more convenient than using execute_code() for these common operations.

    Args:
        doc_name: The name of the document containing the objects.
        operation: The type of boolean operation:
            - "cut": Subtract tool_obj from base_obj (e.g., cutting a hole)
            - "fuse": Combine base_obj and tool_obj (e.g., joining two parts)
            - "common": Find intersection of base_obj and tool_obj
        base_obj_name: The name of the base object (first operand).
        tool_obj_name: The name of the tool object (second operand).
        result_name: Optional name for the result object. If not provided, auto-generates
            a name like "Cut_Base_Tool".
        keep_originals: If True, keeps the original objects visible. If False (default),
            hides them to show only the result.

    Returns:
        A message with the result object name and a screenshot of the result.

    Examples:
        Cut a hole (cylinder) from a box:
        ```json
        {
            "doc_name": "MyDocument",
            "operation": "cut",
            "base_obj_name": "Box",
            "tool_obj_name": "Cylinder",
            "result_name": "BoxWithHole"
        }
        ```

        Join two parts together:
        ```json
        {
            "doc_name": "MyDocument",
            "operation": "fuse",
            "base_obj_name": "Part1",
            "tool_obj_name": "Part2",
            "result_name": "CombinedPart"
        }
        ```

        Find the intersection of two objects:
        ```json
        {
            "doc_name": "MyDocument",
            "operation": "common",
            "base_obj_name": "Sphere",
            "tool_obj_name": "Box",
            "keep_originals": true
        }
        ```
    """
    freecad = get_freecad_connection()
    try:
        res = freecad.boolean_operation(
            doc_name, operation, base_obj_name, tool_obj_name, result_name, keep_originals
        )
        screenshot = freecad.get_active_screenshot()

        if res["success"]:
            response = [
                TextContent(
                    type="text",
                    text=f"Boolean operation '{operation}' completed successfully. "
                         f"Result object: '{res['result_object']}'"
                )
            ]
            return add_screenshot_if_available(response, screenshot)
        else:
            response = [
                TextContent(type="text", text=f"Failed to perform boolean operation: {res['error']}")
            ]
            return add_screenshot_if_available(response, screenshot)
    except Exception as e:
        logger.error(f"Failed to perform boolean operation: {str(e)}")
        return [
            TextContent(type="text", text=f"Failed to perform boolean operation: {str(e)}")
        ]


@mcp.tool()
def create_box(
    ctx: Context,
    doc_name: str,
    name: str,
    length: float,
    width: float,
    height: float,
    position_x: float = 0,
    position_y: float = 0,
    position_z: float = 0,
    color_r: float = None,
    color_g: float = None,
    color_b: float = None,
    color_a: float = 1.0
) -> list[TextContent | ImageContent]:
    """Create a box with simplified parameters.

    This is a convenience wrapper around create_object() that makes box creation simpler
    and more intuitive. All dimensions are in millimeters.

    Args:
        doc_name: The name of the document to create the box in.
        name: The name for the box object.
        length: Box length in mm (X dimension).
        width: Box width in mm (Y dimension).
        height: Box height in mm (Z dimension).
        position_x: X coordinate of the box corner (default: 0).
        position_y: Y coordinate of the box corner (default: 0).
        position_z: Z coordinate of the box corner (default: 0).
        color_r: Red component 0.0-1.0 (optional).
        color_g: Green component 0.0-1.0 (optional).
        color_b: Blue component 0.0-1.0 (optional).
        color_a: Alpha component 0.0-1.0 (default: 1.0).

    Returns:
        A message indicating success or failure and a screenshot.

    Examples:
        Create a simple box at origin:
        ```json
        {
            "doc_name": "MyDocument",
            "name": "MyBox",
            "length": 100,
            "width": 50,
            "height": 25
        }
        ```

        Create a red box at specific position:
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
    """
    freecad = get_freecad_connection()
    try:
        position = {"x": position_x, "y": position_y, "z": position_z}
        color = None
        if color_r is not None and color_g is not None and color_b is not None:
            color = [color_r, color_g, color_b, color_a]

        res = freecad.create_box(doc_name, name, length, width, height, position, color)
        screenshot = freecad.get_active_screenshot()

        if res["success"]:
            response = [
                TextContent(
                    type="text",
                    text=f"Box '{res['object_name']}' created successfully "
                         f"(L={length}, W={width}, H={height} mm)"
                )
            ]
            return add_screenshot_if_available(response, screenshot)
        else:
            response = [
                TextContent(type="text", text=f"Failed to create box: {res['error']}")
            ]
            return add_screenshot_if_available(response, screenshot)
    except Exception as e:
        logger.error(f"Failed to create box: {str(e)}")
        return [
            TextContent(type="text", text=f"Failed to create box: {str(e)}")
        ]


@mcp.tool()
def create_cylinder(
    ctx: Context,
    doc_name: str,
    name: str,
    radius: float,
    height: float,
    position_x: float = 0,
    position_y: float = 0,
    position_z: float = 0,
    color_r: float = None,
    color_g: float = None,
    color_b: float = None,
    color_a: float = 1.0
) -> list[TextContent | ImageContent]:
    """Create a cylinder with simplified parameters.

    This is a convenience wrapper around create_object() that makes cylinder creation simpler
    and more intuitive. All dimensions are in millimeters. The cylinder is created with its
    axis along the Z direction by default.

    Args:
        doc_name: The name of the document to create the cylinder in.
        name: The name for the cylinder object.
        radius: Cylinder radius in mm.
        height: Cylinder height in mm (along Z axis).
        position_x: X coordinate of the cylinder base center (default: 0).
        position_y: Y coordinate of the cylinder base center (default: 0).
        position_z: Z coordinate of the cylinder base center (default: 0).
        color_r: Red component 0.0-1.0 (optional).
        color_g: Green component 0.0-1.0 (optional).
        color_b: Blue component 0.0-1.0 (optional).
        color_a: Alpha component 0.0-1.0 (default: 1.0).

    Returns:
        A message indicating success or failure and a screenshot.

    Examples:
        Create a simple cylinder at origin:
        ```json
        {
            "doc_name": "MyDocument",
            "name": "MyCylinder",
            "radius": 10,
            "height": 30
        }
        ```

        Create a blue cylinder for a mounting hole:
        ```json
        {
            "doc_name": "MyDocument",
            "name": "MountingHole",
            "radius": 2.5,
            "height": 10,
            "position_x": 10,
            "position_y": 0,
            "position_z": 20,
            "color_r": 0.0,
            "color_g": 0.0,
            "color_b": 1.0
        }
        ```
    """
    freecad = get_freecad_connection()
    try:
        position = {"x": position_x, "y": position_y, "z": position_z}
        color = None
        if color_r is not None and color_g is not None and color_b is not None:
            color = [color_r, color_g, color_b, color_a]

        res = freecad.create_cylinder(doc_name, name, radius, height, position, None, color)
        screenshot = freecad.get_active_screenshot()

        if res["success"]:
            response = [
                TextContent(
                    type="text",
                    text=f"Cylinder '{res['object_name']}' created successfully "
                         f"(R={radius}, H={height} mm)"
                )
            ]
            return add_screenshot_if_available(response, screenshot)
        else:
            response = [
                TextContent(type="text", text=f"Failed to create cylinder: {res['error']}")
            ]
            return add_screenshot_if_available(response, screenshot)
    except Exception as e:
        logger.error(f"Failed to create cylinder: {str(e)}")
        return [
            TextContent(type="text", text=f"Failed to create cylinder: {str(e)}")
        ]


@mcp.tool()
def create_fastener(
    ctx: Context,
    doc_name: str,
    name: str,
    fastener_type: str,
    position_x: float = 0,
    position_y: float = 0,
    position_z: float = 0,
    attach_to: str = None,
    diameter: str = "M4",
    length: str = "10"
) -> list[TextContent | ImageContent]:
    """Create a fastener (screw, bolt, nut) using the Fasteners Workbench.

    This tool creates hardware fasteners like screws, bolts, nuts, and washers using the FreeCAD
    Fasteners Workbench. The Fasteners Workbench must be installed in FreeCAD.

    Args:
        doc_name: The name of the document to create the fastener in.
        name: The name for the fastener object.
        fastener_type: The type of fastener to create. Common types:
            - "DIN464": Knurled thumb screw (for tool-less adjustment)
            - "ISO4017": Hex head bolt (standard bolt)
            - "DIN912": Socket head cap screw (Allen bolt)
            - "ISO4032": Hex nut
            - "ISO7380": Button head screw
            - "DIN933": Hex head screw
            - "ISO7089": Plain washer
        position_x: X coordinate of the fastener position (default: 0).
        position_y: Y coordinate of the fastener position (default: 0).
        position_z: Z coordinate of the fastener position (default: 0).
        attach_to: Optional name of object to attach the fastener to (default: None).
        diameter: Fastener diameter as string (e.g., "M3", "M4", "M5", "M6", "M8") (default: "M4").
        length: Fastener length in mm as string (e.g., "6", "8", "10", "12", "16", "20") (default: "10").

    Returns:
        A message indicating success or failure and a screenshot.

    Common Fastener Types:
        - DIN464 (Thumbscrew): For tool-less mounting, common in rack panels
        - ISO4017 (Hex Bolt): General purpose bolts
        - DIN912 (Socket Cap): For precision applications
        - ISO4032 (Hex Nut): Standard nuts
        - ISO7380 (Button Head): Low-profile aesthetic fastening

    Examples:
        Create M4 thumbscrew for faceplate mounting:
        ```json
        {
            "doc_name": "USFF_Tray",
            "name": "Thumbscrew_Left",
            "fastener_type": "DIN464",
            "position_x": 7.9375,
            "position_y": -6,
            "position_z": 22.225,
            "attach_to": "Faceplate_Final",
            "diameter": "M4"
        }
        ```

        Create M5 hex bolt:
        ```json
        {
            "doc_name": "MyProject",
            "name": "MountingBolt",
            "fastener_type": "ISO4017",
            "position_x": 50,
            "position_y": 0,
            "position_z": 10,
            "diameter": "M5",
            "length": "20"
        }
        ```

    Note:
        The Fasteners Workbench will be automatically activated when using this tool.
        If the workbench is not installed, the tool will return an error with installation instructions.
    """
    freecad = get_freecad_connection()
    try:
        position = {"x": position_x, "y": position_y, "z": position_z}

        res = freecad.create_fastener(
            doc_name, name, fastener_type, position, attach_to, diameter, length
        )
        screenshot = freecad.get_active_screenshot()

        if res["success"]:
            response = [
                TextContent(
                    type="text",
                    text=f"Fastener '{res['object_name']}' created successfully "
                         f"(Type: {fastener_type}, Size: {diameter}×{length}mm)"
                )
            ]
            return add_screenshot_if_available(response, screenshot)
        else:
            response = [
                TextContent(type="text", text=f"Failed to create fastener: {res['error']}")
            ]
            return add_screenshot_if_available(response, screenshot)
    except Exception as e:
        logger.error(f"Failed to create fastener: {str(e)}")
        return [
            TextContent(type="text", text=f"Failed to create fastener: {str(e)}")
        ]


@mcp.prompt()
def asset_creation_strategy() -> str:
    return """
Asset Creation Strategy for FreeCAD MCP

When creating content in FreeCAD, always follow these steps:

0. Before starting any task, always use get_objects() to confirm the current state of the document.

1. Utilize the parts library:
   - Check available parts using get_parts_list().
   - If the required part exists in the library, use insert_part_from_library() to insert it into your document.

2. If the appropriate asset is not available in the parts library:
   - Create basic shapes (e.g., cubes, cylinders, spheres) using create_object().
   - Adjust and define detailed properties of the shapes as necessary using edit_object().

3. Always assign clear and descriptive names to objects when adding them to the document.

4. Explicitly set the position, scale, and rotation properties of created or inserted objects using edit_object() to ensure proper spatial relationships.

5. After editing an object, always verify that the set properties have been correctly applied by using get_object().

6. If detailed customization or specialized operations are necessary, use execute_code() to run custom Python scripts.

Only revert to basic creation methods in the following cases:
- When the required asset is not available in the parts library.
- When a basic shape is explicitly requested.
- When creating complex shapes requires custom scripting.
"""


def main():
    """Run the MCP server"""
    global _only_text_feedback
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--only-text-feedback", action="store_true", help="Only return text feedback")
    args = parser.parse_args()
    _only_text_feedback = args.only_text_feedback
    logger.info(f"Only text feedback: {_only_text_feedback}")
    mcp.run()