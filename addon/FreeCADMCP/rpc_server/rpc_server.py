import FreeCAD
import FreeCADGui
import ObjectsFem

import contextlib
import queue
import base64
import io
import os
import tempfile
import threading
from dataclasses import dataclass, field
from typing import Any
from xmlrpc.server import SimpleXMLRPCServer

from PySide import QtCore

from .parts_library import get_parts_list, insert_part_from_library
from .serialize import serialize_object

rpc_server_thread = None
rpc_server_instance = None

# GUI task queue
rpc_request_queue = queue.Queue()
rpc_response_queue = queue.Queue()


def process_gui_tasks():
    while not rpc_request_queue.empty():
        task = rpc_request_queue.get()
        res = task()
        if res is not None:
            rpc_response_queue.put(res)
    QtCore.QTimer.singleShot(500, process_gui_tasks)


@dataclass
class Object:
    name: str
    type: str | None = None
    analysis: str | None = None
    properties: dict[str, Any] = field(default_factory=dict)


def set_object_property(
    doc: FreeCAD.Document, obj: FreeCAD.DocumentObject, properties: dict[str, Any]
):
    for prop, val in properties.items():
        try:
            if prop in obj.PropertiesList:
                if prop == "Placement" and isinstance(val, dict):
                    if "Base" in val:
                        pos = val["Base"]
                    elif "Position" in val:
                        pos = val["Position"]
                    else:
                        pos = {}
                    rot = val.get("Rotation", {})
                    placement = FreeCAD.Placement(
                        FreeCAD.Vector(
                            pos.get("x", 0),
                            pos.get("y", 0),
                            pos.get("z", 0),
                        ),
                        FreeCAD.Rotation(
                            FreeCAD.Vector(
                                rot.get("Axis", {}).get("x", 0),
                                rot.get("Axis", {}).get("y", 0),
                                rot.get("Axis", {}).get("z", 1),
                            ),
                            rot.get("Angle", 0),
                        ),
                    )
                    setattr(obj, prop, placement)

                elif isinstance(getattr(obj, prop), FreeCAD.Vector) and isinstance(
                    val, dict
                ):
                    vector = FreeCAD.Vector(
                        val.get("x", 0), val.get("y", 0), val.get("z", 0)
                    )
                    setattr(obj, prop, vector)

                elif prop in ["Base", "Tool", "Source", "Profile"] and isinstance(
                    val, str
                ):
                    ref_obj = doc.getObject(val)
                    if ref_obj:
                        setattr(obj, prop, ref_obj)
                    else:
                        raise ValueError(f"Referenced object '{val}' not found.")

                elif prop == "References" and isinstance(val, list):
                    refs = []
                    for ref_name, face in val:
                        ref_obj = doc.getObject(ref_name)
                        if ref_obj:
                            refs.append((ref_obj, face))
                        else:
                            raise ValueError(f"Referenced object '{ref_name}' not found.")
                    setattr(obj, prop, refs)

                else:
                    setattr(obj, prop, val)
            # ShapeColor is a property of the ViewObject
            elif prop == "ShapeColor" and isinstance(val, (list, tuple)):
                setattr(obj.ViewObject, prop, (float(val[0]), float(val[1]), float(val[2]), float(val[3])))

            elif prop == "ViewObject" and isinstance(val, dict):
                for k, v in val.items():
                    if k == "ShapeColor":
                        setattr(obj.ViewObject, k, (float(v[0]), float(v[1]), float(v[2]), float(v[3])))
                    else:
                        setattr(obj.ViewObject, k, v)

            else:
                setattr(obj, prop, val)

        except Exception as e:
            FreeCAD.Console.PrintError(f"Property '{prop}' assignment error: {e}\n")


class FreeCADRPC:
    """RPC server for FreeCAD"""

    def ping(self):
        return True

    def create_document(self, name="New_Document"):
        rpc_request_queue.put(lambda: self._create_document_gui(name))
        res = rpc_response_queue.get()
        if res is True:
            return {"success": True, "document_name": name}
        else:
            return {"success": False, "error": res}

    def create_object(self, doc_name, obj_data: dict[str, Any]):
        obj = Object(
            name=obj_data.get("Name", "New_Object"),
            type=obj_data["Type"],
            analysis=obj_data.get("Analysis", None),
            properties=obj_data.get("Properties", {}),
        )
        rpc_request_queue.put(lambda: self._create_object_gui(doc_name, obj))
        res = rpc_response_queue.get()
        if res is True:
            return {"success": True, "object_name": obj.name}
        else:
            return {"success": False, "error": res}

    def edit_object(self, doc_name: str, obj_name: str, properties: dict[str, Any]) -> dict[str, Any]:
        obj = Object(
            name=obj_name,
            properties=properties.get("Properties", {}),
        )
        rpc_request_queue.put(lambda: self._edit_object_gui(doc_name, obj))
        res = rpc_response_queue.get()
        if res is True:
            return {"success": True, "object_name": obj.name}
        else:
            return {"success": False, "error": res}

    def delete_object(self, doc_name: str, obj_name: str):
        rpc_request_queue.put(lambda: self._delete_object_gui(doc_name, obj_name))
        res = rpc_response_queue.get()
        if res is True:
            return {"success": True, "object_name": obj_name}
        else:
            return {"success": False, "error": res}

    def execute_code(self, code: str) -> dict[str, Any]:
        output_buffer = io.StringIO()
        def task():
            try:
                with contextlib.redirect_stdout(output_buffer):
                    exec(code, globals())
                FreeCAD.Console.PrintMessage("Python code executed successfully.\n")
                return True
            except Exception as e:
                FreeCAD.Console.PrintError(
                    f"Error executing Python code: {e}\n"
                )
                return f"Error executing Python code: {e}\n"

        rpc_request_queue.put(task)
        res = rpc_response_queue.get()
        if res is True:
            return {
                "success": True,
                "message": "Python code execution scheduled. \nOutput: " + output_buffer.getvalue()
            }
        else:
            return {"success": False, "error": res}

    def get_objects(self, doc_name):
        doc = FreeCAD.getDocument(doc_name)
        if doc:
            return [serialize_object(obj) for obj in doc.Objects]
        else:
            return []

    def get_object(self, doc_name, obj_name):
        doc = FreeCAD.getDocument(doc_name)
        if doc:
            return serialize_object(doc.getObject(obj_name))
        else:
            return None

    def insert_part_from_library(self, relative_path):
        rpc_request_queue.put(lambda: self._insert_part_from_library(relative_path))
        res = rpc_response_queue.get()
        if res is True:
            return {"success": True, "message": "Part inserted from library."}
        else:
            return {"success": False, "error": res}

    def list_documents(self):
        return list(FreeCAD.listDocuments().keys())

    def get_parts_list(self):
        return get_parts_list()

    def activate_workbench(self, workbench_name: str) -> dict[str, Any]:
        """Activate a FreeCAD workbench.

        Args:
            workbench_name: Name of the workbench to activate (e.g., "FastenersWorkbench", "PartDesign", "Draft")

        Returns:
            Success status and workbench information
        """
        rpc_request_queue.put(lambda: self._activate_workbench_gui(workbench_name))
        res = rpc_response_queue.get()
        if res is True:
            return {
                "success": True,
                "message": f"Workbench '{workbench_name}' activated successfully",
                "workbench": workbench_name
            }
        else:
            return {"success": False, "error": res}

    def boolean_operation(
        self,
        doc_name: str,
        operation: str,
        base_obj_name: str,
        tool_obj_name: str,
        result_name: str = None,
        keep_originals: bool = False
    ) -> dict[str, Any]:
        """Perform boolean operation between two objects.

        Args:
            doc_name: Document name
            operation: "cut", "fuse", or "common"
            base_obj_name: First object name
            tool_obj_name: Second object name
            result_name: Name for result object (auto-generated if None)
            keep_originals: If True, keep original objects

        Returns:
            Success status and result object name
        """
        rpc_request_queue.put(
            lambda: self._boolean_operation_gui(
                doc_name, operation, base_obj_name, tool_obj_name, result_name, keep_originals
            )
        )
        res = rpc_response_queue.get()
        if isinstance(res, str):
            return {"success": False, "error": res}
        else:
            return {"success": True, "result_object": res["result_object"], "message": res["message"]}

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
        """Create a box with simplified parameters.

        Args:
            doc_name: Document name
            name: Object name
            length: Box length (X dimension)
            width: Box width (Y dimension)
            height: Box height (Z dimension)
            position: Optional position dict with x, y, z keys
            color: Optional RGBA color [R, G, B, A] (0.0-1.0)

        Returns:
            Success status and object name
        """
        obj_data = {
            "Name": name,
            "Type": "Part::Box",
            "Properties": {
                "Length": length,
                "Width": width,
                "Height": height
            }
        }

        if position:
            obj_data["Properties"]["Placement"] = {
                "Base": {"x": position.get("x", 0), "y": position.get("y", 0), "z": position.get("z", 0)}
            }

        if color:
            obj_data["Properties"]["ViewObject"] = {
                "ShapeColor": color
            }

        return self.create_object(doc_name, obj_data)

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
        """Create a cylinder with simplified parameters.

        Args:
            doc_name: Document name
            name: Object name
            radius: Cylinder radius
            height: Cylinder height
            position: Optional position dict with x, y, z keys
            direction: Optional direction dict with x, y, z keys (default: Z-axis)
            color: Optional RGBA color [R, G, B, A] (0.0-1.0)

        Returns:
            Success status and object name
        """
        obj_data = {
            "Name": name,
            "Type": "Part::Cylinder",
            "Properties": {
                "Radius": radius,
                "Height": height
            }
        }

        if position or direction:
            placement = {"Base": {}}
            if position:
                placement["Base"] = {"x": position.get("x", 0), "y": position.get("y", 0), "z": position.get("z", 0)}
            else:
                placement["Base"] = {"x": 0, "y": 0, "z": 0}

            if direction:
                # Calculate rotation from direction vector
                # For now, just store the direction - FreeCAD will handle rotation
                placement["Rotation"] = {
                    "Axis": {"x": direction.get("x", 0), "y": direction.get("y", 0), "z": direction.get("z", 1)},
                    "Angle": 0
                }

            obj_data["Properties"]["Placement"] = placement

        if color:
            obj_data["Properties"]["ViewObject"] = {
                "ShapeColor": color
            }

        return self.create_object(doc_name, obj_data)

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
        """Create a fastener using FastenersWorkbench.

        Args:
            doc_name: Document name
            name: Object name for the fastener
            fastener_type: Fastener type (e.g., "DIN464", "ISO4017", "DIN912")
            position: Optional position dict with x, y, z keys
            attach_to: Optional object name to attach fastener to
            diameter: Fastener diameter (e.g., "M3", "M4", "M5", "M6")
            length: Fastener length in mm (as string)

        Returns:
            Success status and object name
        """
        rpc_request_queue.put(
            lambda: self._create_fastener_gui(
                doc_name, name, fastener_type, position, attach_to, diameter, length
            )
        )
        res = rpc_response_queue.get()
        if isinstance(res, str):
            return {"success": False, "error": res}
        else:
            return {
                "success": True,
                "object_name": res["object_name"],
                "fastener_type": fastener_type,
                "position": position or {"x": 0, "y": 0, "z": 0},
                "message": res["message"]
            }

    def get_active_screenshot(self, view_name: str = "Isometric") -> str:
        """Get a screenshot of the active view.

        Returns a base64-encoded string of the screenshot or None if a screenshot
        cannot be captured (e.g., when in TechDraw or Spreadsheet view).
        """
        # First check if the active view supports screenshots
        def check_view_supports_screenshots():
            try:
                active_view = FreeCADGui.ActiveDocument.ActiveView
                if active_view is None:
                    FreeCAD.Console.PrintWarning("No active view available\n")
                    return False
                
                view_type = type(active_view).__name__
                has_save_image = hasattr(active_view, 'saveImage')
                FreeCAD.Console.PrintMessage(f"View type: {view_type}, Has saveImage: {has_save_image}\n")
                return has_save_image
            except Exception as e:
                FreeCAD.Console.PrintError(f"Error checking view capabilities: {e}\n")
                return False
                
        rpc_request_queue.put(check_view_supports_screenshots)
        supports_screenshots = rpc_response_queue.get()
        
        if not supports_screenshots:
            FreeCAD.Console.PrintWarning("Current view does not support screenshots\n")
            return None
            
        # If view supports screenshots, proceed with capture
        fd, tmp_path = tempfile.mkstemp(suffix=".png")
        os.close(fd)
        rpc_request_queue.put(
            lambda: self._save_active_screenshot(tmp_path, view_name)
        )
        res = rpc_response_queue.get()
        if res is True:
            try:
                with open(tmp_path, "rb") as image_file:
                    image_bytes = image_file.read()
                    encoded = base64.b64encode(image_bytes).decode("utf-8")
            finally:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
            return encoded
        else:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
            FreeCAD.Console.PrintWarning(f"Failed to capture screenshot: {res}\n")
            return None

    def _create_document_gui(self, name):
        doc = FreeCAD.newDocument(name)
        doc.recompute()
        FreeCAD.Console.PrintMessage(f"Document '{name}' created via RPC.\n")
        return True

    def _create_object_gui(self, doc_name, obj: Object):
        doc = FreeCAD.getDocument(doc_name)
        if not doc:
            available_docs = list(FreeCAD.listDocuments().keys())
            error_msg = f"Document '{doc_name}' not found."
            if available_docs:
                error_msg += f" Available documents: {', '.join(available_docs)}"
            else:
                error_msg += " No documents are currently open."
            FreeCAD.Console.PrintError(error_msg + "\n")
            return error_msg

        # Check if object with same name already exists
        if doc.getObject(obj.name):
            error_msg = f"Object '{obj.name}' already exists in document '{doc_name}'."
            FreeCAD.Console.PrintError(error_msg + "\n")
            return error_msg

        try:
            if obj.type == "Fem::FemMeshGmsh" and obj.analysis:
                from femmesh.gmshtools import GmshTools
                res = getattr(doc, obj.analysis).addObject(ObjectsFem.makeMeshGmsh(doc, obj.name))[0]
                if "Part" in obj.properties:
                    target_obj = doc.getObject(obj.properties["Part"])
                    if target_obj:
                        res.Part = target_obj
                    else:
                        available_objs = [o.Label for o in doc.Objects]
                        raise ValueError(
                            f"Referenced object '{obj.properties['Part']}' not found. "
                            f"Available objects: {', '.join(available_objs[:10])}"
                            + ("..." if len(available_objs) > 10 else "")
                        )
                    del obj.properties["Part"]
                else:
                    raise ValueError("'Part' property not found in properties.")

                for param, value in obj.properties.items():
                    if hasattr(res, param):
                        setattr(res, param, value)
                doc.recompute()

                gmsh_tools = GmshTools(res)
                gmsh_tools.create_mesh()
                FreeCAD.Console.PrintMessage(
                    f"FEM Mesh '{res.Name}' generated successfully in '{doc_name}'.\n"
                )
            elif obj.type.startswith("Fem::"):
                fem_make_methods = {
                    "MaterialCommon": ObjectsFem.makeMaterialSolid,
                    "AnalysisPython": ObjectsFem.makeAnalysis,
                }
                obj_type_short = obj.type.split("::")[1]
                method_name = "make" + obj_type_short
                make_method = fem_make_methods.get(obj_type_short, getattr(ObjectsFem, method_name, None))

                if callable(make_method):
                    res = make_method(doc, obj.name)
                    set_object_property(doc, res, obj.properties)
                    FreeCAD.Console.PrintMessage(
                        f"FEM object '{res.Name}' created with '{method_name}'.\n"
                    )
                else:
                    raise ValueError(f"No creation method '{method_name}' found in ObjectsFem.")
                if obj.type != "Fem::AnalysisPython" and obj.analysis:
                    getattr(doc, obj.analysis).addObject(res)
            else:
                res = doc.addObject(obj.type, obj.name)
                set_object_property(doc, res, obj.properties)

                # Set ViewObject visibility (NEW - addresses invisible objects issue)
                if hasattr(res, "ViewObject") and res.ViewObject:
                    res.ViewObject.Visibility = True
                    FreeCAD.Console.PrintMessage(f"ViewObject visibility set for '{res.Name}'.\n")

                FreeCAD.Console.PrintMessage(
                    f"{res.TypeId} '{res.Name}' added to '{doc_name}' via RPC.\n"
                )

            doc.recompute()
            return True
        except Exception as e:
            error_msg = f"Failed to create object '{obj.name}': {str(e)}"
            FreeCAD.Console.PrintError(error_msg + "\n")
            return error_msg

    def _edit_object_gui(self, doc_name: str, obj: Object):
        doc = FreeCAD.getDocument(doc_name)
        if not doc:
            FreeCAD.Console.PrintError(f"Document '{doc_name}' not found.\n")
            return f"Document '{doc_name}' not found.\n"

        obj_ins = doc.getObject(obj.name)
        if not obj_ins:
            FreeCAD.Console.PrintError(f"Object '{obj.name}' not found in document '{doc_name}'.\n")
            return f"Object '{obj.name}' not found in document '{doc_name}'.\n"

        try:
            # For Fem::ConstraintFixed
            if hasattr(obj_ins, "References") and "References" in obj.properties:
                refs = []
                for ref_name, face in obj.properties["References"]:
                    ref_obj = doc.getObject(ref_name)
                    if ref_obj:
                        refs.append((ref_obj, face))
                    else:
                        raise ValueError(f"Referenced object '{ref_name}' not found.")
                obj_ins.References = refs
                FreeCAD.Console.PrintMessage(
                    f"References updated for '{obj.name}' in '{doc_name}'.\n"
                )
                # delete References from properties
                del obj.properties["References"]
            set_object_property(doc, obj_ins, obj.properties)
            doc.recompute()
            FreeCAD.Console.PrintMessage(f"Object '{obj.name}' updated via RPC.\n")
            return True
        except Exception as e:
            return str(e)

    def _delete_object_gui(self, doc_name: str, obj_name: str):
        doc = FreeCAD.getDocument(doc_name)
        if not doc:
            FreeCAD.Console.PrintError(f"Document '{doc_name}' not found.\n")
            return f"Document '{doc_name}' not found.\n"

        try:
            doc.removeObject(obj_name)
            doc.recompute()
            FreeCAD.Console.PrintMessage(f"Object '{obj_name}' deleted via RPC.\n")
            return True
        except Exception as e:
            return str(e)

    def _insert_part_from_library(self, relative_path):
        try:
            insert_part_from_library(relative_path)
            return True
        except Exception as e:
            return str(e)

    def _activate_workbench_gui(self, workbench_name: str):
        """Activate workbench in GUI thread"""
        try:
            # List of common workbenches for validation
            common_workbenches = [
                "FastenersWorkbench", "PartDesign", "Draft", "Sketcher",
                "Arch", "Path", "Part", "Fem", "Drawing", "Mesh", "Points",
                "Raytracing", "Spreadsheet", "Surface", "TechDraw", "Web"
            ]

            # Get list of available workbenches
            available_workbenches = FreeCADGui.listWorkbenches()

            if workbench_name not in available_workbenches:
                return (
                    f"Workbench '{workbench_name}' not found. "
                    f"Available workbenches: {', '.join(sorted(available_workbenches.keys()))}"
                )

            # Activate the workbench
            FreeCADGui.activateWorkbench(workbench_name)
            FreeCAD.Console.PrintMessage(f"Workbench '{workbench_name}' activated via RPC.\n")
            return True
        except Exception as e:
            error_msg = f"Failed to activate workbench '{workbench_name}': {str(e)}"
            FreeCAD.Console.PrintError(error_msg + "\n")
            return error_msg

    def _boolean_operation_gui(
        self,
        doc_name: str,
        operation: str,
        base_obj_name: str,
        tool_obj_name: str,
        result_name: str = None,
        keep_originals: bool = False
    ):
        """Perform boolean operation in GUI thread"""
        try:
            doc = FreeCAD.getDocument(doc_name)
            if not doc:
                available_docs = list(FreeCAD.listDocuments().keys())
                error_msg = f"Document '{doc_name}' not found."
                if available_docs:
                    error_msg += f" Available documents: {', '.join(available_docs)}"
                return error_msg

            # Get objects
            base_obj = doc.getObject(base_obj_name)
            tool_obj = doc.getObject(tool_obj_name)

            if not base_obj:
                available_objs = [o.Label for o in doc.Objects]
                return (
                    f"Base object '{base_obj_name}' not found in document '{doc_name}'. "
                    f"Available objects: {', '.join(available_objs[:10])}"
                    + ("..." if len(available_objs) > 10 else "")
                )

            if not tool_obj:
                available_objs = [o.Label for o in doc.Objects]
                return (
                    f"Tool object '{tool_obj_name}' not found in document '{doc_name}'. "
                    f"Available objects: {', '.join(available_objs[:10])}"
                    + ("..." if len(available_objs) > 10 else "")
                )

            # Validate operation
            if operation not in ["cut", "fuse", "common"]:
                return f"Invalid operation '{operation}'. Must be 'cut', 'fuse', or 'common'."

            # Perform boolean operation
            if operation == "cut":
                result_shape = base_obj.Shape.cut(tool_obj.Shape)
                op_name = "Cut"
            elif operation == "fuse":
                result_shape = base_obj.Shape.fuse(tool_obj.Shape)
                op_name = "Fuse"
            else:  # common
                result_shape = base_obj.Shape.common(tool_obj.Shape)
                op_name = "Common"

            # Create result object
            if result_name is None:
                result_name = f"{op_name}_{base_obj_name}_{tool_obj_name}"

            result_obj = doc.addObject("Part::Feature", result_name)
            result_obj.Shape = result_shape

            # Set ViewObject properties
            if hasattr(result_obj, "ViewObject") and result_obj.ViewObject:
                result_obj.ViewObject.Visibility = True

            # Hide or delete originals
            if not keep_originals:
                if hasattr(base_obj, "ViewObject") and base_obj.ViewObject:
                    base_obj.ViewObject.Visibility = False
                if hasattr(tool_obj, "ViewObject") and tool_obj.ViewObject:
                    tool_obj.ViewObject.Visibility = False

            doc.recompute()

            FreeCAD.Console.PrintMessage(
                f"Boolean operation '{operation}' completed: '{result_obj.Name}' created.\n"
            )
            return {
                "result_object": result_obj.Name,
                "message": f"Boolean {operation} completed successfully"
            }

        except Exception as e:
            error_msg = f"Failed to perform boolean operation: {str(e)}"
            FreeCAD.Console.PrintError(error_msg + "\n")
            return error_msg

    def _create_fastener_gui(
        self,
        doc_name: str,
        name: str,
        fastener_type: str,
        position: dict[str, float] = None,
        attach_to: str = None,
        diameter: str = "M4",
        length: str = "10"
    ):
        """Create fastener in GUI thread"""
        try:
            doc = FreeCAD.getDocument(doc_name)
            if not doc:
                available_docs = list(FreeCAD.listDocuments().keys())
                error_msg = f"Document '{doc_name}' not found."
                if available_docs:
                    error_msg += f" Available documents: {', '.join(available_docs)}"
                return error_msg

            # Ensure FastenersWorkbench is activated
            available_workbenches = FreeCADGui.listWorkbenches()
            if "FastenersWorkbench" not in available_workbenches:
                return (
                    "FastenersWorkbench not found. "
                    "Please install the Fasteners Workbench add-on from FreeCAD."
                )

            # Activate FastenersWorkbench
            FreeCADGui.activateWorkbench("FastenersWorkbench")

            # Import FastenersCmd
            import FastenersCmd

            # Get attach_to object if specified
            attach_obj = None
            if attach_to:
                attach_obj = doc.getObject(attach_to)
                if not attach_obj:
                    available_objs = [o.Label for o in doc.Objects]
                    return (
                        f"Attach object '{attach_to}' not found in document '{doc_name}'. "
                        f"Available objects: {', '.join(available_objs[:10])}"
                        + ("..." if len(available_objs) > 10 else "")
                    )

            # Create fastener object
            screw_obj = doc.addObject("Part::FeaturePython", name)

            # Use FSScrewObject with correct signature
            # Signature: FSScrewObject(obj, fastener_type, attach_to_obj)
            FastenersCmd.FSScrewObject(screw_obj, fastener_type, attach_obj)

            # Set position if provided
            if position:
                screw_obj.Placement.Base = FreeCAD.Vector(
                    position.get("x", 0),
                    position.get("y", 0),
                    position.get("z", 0)
                )

            # Set ViewObject properties for visibility
            if hasattr(screw_obj, "ViewObject") and screw_obj.ViewObject:
                screw_obj.ViewObject.Visibility = True

            doc.recompute()

            FreeCAD.Console.PrintMessage(
                f"Fastener '{screw_obj.Name}' ({fastener_type}) created successfully.\n"
            )
            return {
                "object_name": screw_obj.Name,
                "message": f"Fastener '{fastener_type}' created successfully"
            }

        except Exception as e:
            error_msg = f"Failed to create fastener: {str(e)}"
            FreeCAD.Console.PrintError(error_msg + "\n")
            return error_msg

    # ============================================================
    # NEW SKETCH AND EXTRUSION METHODS
    # ============================================================
    
    def create_sketch(
        self,
        doc_name: str,
        name: str,
        plane: str = "XY",
        origin: dict[str, float] = None,
        body_name: str = None
    ) -> dict[str, Any]:
        """Create a new sketch on a specified plane.
        
        Args:
            doc_name: Document name
            name: Sketch name
            plane: Plane to create sketch on - "XY", "XZ", or "YZ"
            origin: Optional origin offset {x, y, z}
            body_name: Optional PartDesign Body to add sketch to
        
        Returns:
            Success status and sketch name
        """
        rpc_request_queue.put(
            lambda: self._create_sketch_gui(doc_name, name, plane, origin, body_name)
        )
        res = rpc_response_queue.get()
        if isinstance(res, str):
            return {"success": False, "error": res}
        return {"success": True, "sketch_name": res["sketch_name"], "message": res["message"]}
    
    def _create_sketch_gui(
        self,
        doc_name: str,
        name: str,
        plane: str,
        origin: dict[str, float],
        body_name: str
    ):
        """Create sketch in GUI thread"""
        try:
            import Part
            import Sketcher
            
            doc = FreeCAD.getDocument(doc_name)
            if not doc:
                return f"Document '{doc_name}' not found."
            
            # Get or create body if specified
            body = None
            if body_name:
                body = doc.getObject(body_name)
                if not body:
                    # Create body if it doesn't exist
                    body = doc.addObject('PartDesign::Body', body_name)
                    FreeCAD.Console.PrintMessage(f"Created PartDesign Body '{body_name}'.\n")
            
            # Create sketch
            if body:
                sketch = body.newObject('Sketcher::SketchObject', name)
            else:
                sketch = doc.addObject('Sketcher::SketchObject', name)
            
            # Set placement based on plane
            origin_x = origin.get("x", 0) if origin else 0
            origin_y = origin.get("y", 0) if origin else 0
            origin_z = origin.get("z", 0) if origin else 0
            
            if plane.upper() == "XY":
                # Default - no rotation needed
                sketch.Placement = FreeCAD.Placement(
                    FreeCAD.Vector(origin_x, origin_y, origin_z),
                    FreeCAD.Rotation(FreeCAD.Vector(0, 0, 1), 0)
                )
            elif plane.upper() == "XZ":
                # Rotate 90° around X axis
                sketch.Placement = FreeCAD.Placement(
                    FreeCAD.Vector(origin_x, origin_y, origin_z),
                    FreeCAD.Rotation(FreeCAD.Vector(1, 0, 0), 90)
                )
            elif plane.upper() == "YZ":
                # Rotate 90° around Y axis
                sketch.Placement = FreeCAD.Placement(
                    FreeCAD.Vector(origin_x, origin_y, origin_z),
                    FreeCAD.Rotation(FreeCAD.Vector(0, 1, 0), -90)
                )
            else:
                return f"Invalid plane '{plane}'. Use 'XY', 'XZ', or 'YZ'."
            
            doc.recompute()
            FreeCAD.Console.PrintMessage(f"Sketch '{name}' created on {plane} plane.\n")
            return {"sketch_name": name, "message": f"Sketch created on {plane} plane"}
            
        except Exception as e:
            error_msg = f"Failed to create sketch: {str(e)}"
            FreeCAD.Console.PrintError(error_msg + "\n")
            return error_msg
    
    def add_sketch_geometry(
        self,
        doc_name: str,
        sketch_name: str,
        geometry: list[dict[str, Any]],
        construction: bool = False
    ) -> dict[str, Any]:
        """Add geometry to a sketch.
        
        Args:
            doc_name: Document name
            sketch_name: Sketch name
            geometry: List of geometry definitions:
                - {"type": "line", "x1": 0, "y1": 0, "x2": 10, "y2": 0}
                - {"type": "rectangle", "x": -10, "y": -10, "width": 20, "height": 20}
                - {"type": "circle", "cx": 0, "cy": 0, "radius": 5}
                - {"type": "arc", "cx": 0, "cy": 0, "radius": 5, "start_angle": 0, "end_angle": 90}
            construction: Whether geometry is construction geometry
        
        Returns:
            Success status and geometry IDs
        """
        rpc_request_queue.put(
            lambda: self._add_sketch_geometry_gui(doc_name, sketch_name, geometry, construction)
        )
        res = rpc_response_queue.get()
        if isinstance(res, str):
            return {"success": False, "error": res}
        return {"success": True, "geometry_ids": res["geometry_ids"], "message": res["message"]}
    
    def _add_sketch_geometry_gui(
        self,
        doc_name: str,
        sketch_name: str,
        geometry: list[dict[str, Any]],
        construction: bool
    ):
        """Add geometry to sketch in GUI thread"""
        try:
            import Part
            import Sketcher
            import math
            
            doc = FreeCAD.getDocument(doc_name)
            if not doc:
                return f"Document '{doc_name}' not found."
            
            sketch = doc.getObject(sketch_name)
            if not sketch:
                return f"Sketch '{sketch_name}' not found."
            
            if not hasattr(sketch, 'addGeometry'):
                return f"Object '{sketch_name}' is not a valid sketch."
            
            geometry_ids = []
            
            for geom in geometry:
                geom_type = geom.get("type", "").lower()
                
                if geom_type == "line":
                    x1 = geom.get("x1", 0)
                    y1 = geom.get("y1", 0)
                    x2 = geom.get("x2", 0)
                    y2 = geom.get("y2", 0)
                    line = Part.LineSegment(
                        FreeCAD.Vector(x1, y1, 0),
                        FreeCAD.Vector(x2, y2, 0)
                    )
                    gid = sketch.addGeometry(line, construction)
                    geometry_ids.append(gid)
                    
                elif geom_type == "rectangle":
                    x = geom.get("x", 0)
                    y = geom.get("y", 0)
                    w = geom.get("width", 10)
                    h = geom.get("height", 10)
                    # Create 4 lines for rectangle
                    l1 = Part.LineSegment(FreeCAD.Vector(x, y, 0), FreeCAD.Vector(x + w, y, 0))
                    l2 = Part.LineSegment(FreeCAD.Vector(x + w, y, 0), FreeCAD.Vector(x + w, y + h, 0))
                    l3 = Part.LineSegment(FreeCAD.Vector(x + w, y + h, 0), FreeCAD.Vector(x, y + h, 0))
                    l4 = Part.LineSegment(FreeCAD.Vector(x, y + h, 0), FreeCAD.Vector(x, y, 0))
                    
                    id1 = sketch.addGeometry(l1, construction)
                    id2 = sketch.addGeometry(l2, construction)
                    id3 = sketch.addGeometry(l3, construction)
                    id4 = sketch.addGeometry(l4, construction)
                    
                    # Add coincident constraints to close rectangle
                    sketch.addConstraint(Sketcher.Constraint('Coincident', id1, 2, id2, 1))
                    sketch.addConstraint(Sketcher.Constraint('Coincident', id2, 2, id3, 1))
                    sketch.addConstraint(Sketcher.Constraint('Coincident', id3, 2, id4, 1))
                    sketch.addConstraint(Sketcher.Constraint('Coincident', id4, 2, id1, 1))
                    
                    geometry_ids.extend([id1, id2, id3, id4])
                    
                elif geom_type == "circle":
                    cx = geom.get("cx", 0)
                    cy = geom.get("cy", 0)
                    r = geom.get("radius", 5)
                    circle = Part.Circle(
                        FreeCAD.Vector(cx, cy, 0),
                        FreeCAD.Vector(0, 0, 1),
                        r
                    )
                    gid = sketch.addGeometry(circle, construction)
                    geometry_ids.append(gid)
                    
                elif geom_type == "arc":
                    cx = geom.get("cx", 0)
                    cy = geom.get("cy", 0)
                    r = geom.get("radius", 5)
                    start_angle = math.radians(geom.get("start_angle", 0))
                    end_angle = math.radians(geom.get("end_angle", 90))
                    
                    arc = Part.ArcOfCircle(
                        Part.Circle(
                            FreeCAD.Vector(cx, cy, 0),
                            FreeCAD.Vector(0, 0, 1),
                            r
                        ),
                        start_angle,
                        end_angle
                    )
                    gid = sketch.addGeometry(arc, construction)
                    geometry_ids.append(gid)
                    
                else:
                    return f"Unknown geometry type: '{geom_type}'"
            
            doc.recompute()
            FreeCAD.Console.PrintMessage(
                f"Added {len(geometry_ids)} geometry elements to sketch '{sketch_name}'.\n"
            )
            return {"geometry_ids": geometry_ids, "message": f"Added {len(geometry_ids)} geometry elements"}
            
        except Exception as e:
            error_msg = f"Failed to add geometry: {str(e)}"
            FreeCAD.Console.PrintError(error_msg + "\n")
            return error_msg
    
    def add_sketch_constraints(
        self,
        doc_name: str,
        sketch_name: str,
        constraints: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Add constraints to a sketch.
        
        Args:
            doc_name: Document name
            sketch_name: Sketch name
            constraints: List of constraint definitions:
                - {"type": "horizontal", "geometry_id": 0}
                - {"type": "vertical", "geometry_id": 0}
                - {"type": "coincident", "id1": 0, "point1": 2, "id2": 1, "point2": 1}
                - {"type": "distance", "geometry_id": 0, "value": 20.0}
                - {"type": "radius", "geometry_id": 0, "value": 5.0}
                - {"type": "equal", "id1": 0, "id2": 1}
                - {"type": "perpendicular", "id1": 0, "id2": 1}
                - {"type": "fix", "geometry_id": 0, "point": 1}  (point 1=start, 2=end, 3=center)
        
        Returns:
            Success status and constraint count
        """
        rpc_request_queue.put(
            lambda: self._add_sketch_constraints_gui(doc_name, sketch_name, constraints)
        )
        res = rpc_response_queue.get()
        if isinstance(res, str):
            return {"success": False, "error": res}
        return {"success": True, "constraint_count": res["constraint_count"], "message": res["message"]}
    
    def _add_sketch_constraints_gui(
        self,
        doc_name: str,
        sketch_name: str,
        constraints: list[dict[str, Any]]
    ):
        """Add constraints to sketch in GUI thread"""
        try:
            import Sketcher
            
            doc = FreeCAD.getDocument(doc_name)
            if not doc:
                return f"Document '{doc_name}' not found."
            
            sketch = doc.getObject(sketch_name)
            if not sketch:
                return f"Sketch '{sketch_name}' not found."
            
            constraint_count = 0
            
            for c in constraints:
                c_type = c.get("type", "").lower()
                
                if c_type == "horizontal":
                    gid = c.get("geometry_id", 0)
                    sketch.addConstraint(Sketcher.Constraint('Horizontal', gid))
                    constraint_count += 1
                    
                elif c_type == "vertical":
                    gid = c.get("geometry_id", 0)
                    sketch.addConstraint(Sketcher.Constraint('Vertical', gid))
                    constraint_count += 1
                    
                elif c_type == "coincident":
                    id1 = c.get("id1", 0)
                    pt1 = c.get("point1", 2)  # default: end point
                    id2 = c.get("id2", 1)
                    pt2 = c.get("point2", 1)  # default: start point
                    sketch.addConstraint(Sketcher.Constraint('Coincident', id1, pt1, id2, pt2))
                    constraint_count += 1
                    
                elif c_type == "distance":
                    gid = c.get("geometry_id", 0)
                    value = c.get("value", 10.0)
                    sketch.addConstraint(Sketcher.Constraint('Distance', gid, value))
                    constraint_count += 1
                    
                elif c_type == "radius":
                    gid = c.get("geometry_id", 0)
                    value = c.get("value", 5.0)
                    sketch.addConstraint(Sketcher.Constraint('Radius', gid, value))
                    constraint_count += 1
                    
                elif c_type == "equal":
                    id1 = c.get("id1", 0)
                    id2 = c.get("id2", 1)
                    sketch.addConstraint(Sketcher.Constraint('Equal', id1, id2))
                    constraint_count += 1
                    
                elif c_type == "perpendicular":
                    id1 = c.get("id1", 0)
                    id2 = c.get("id2", 1)
                    sketch.addConstraint(Sketcher.Constraint('Perpendicular', id1, id2))
                    constraint_count += 1
                    
                elif c_type == "parallel":
                    id1 = c.get("id1", 0)
                    id2 = c.get("id2", 1)
                    sketch.addConstraint(Sketcher.Constraint('Parallel', id1, id2))
                    constraint_count += 1
                    
                elif c_type == "fix":
                    gid = c.get("geometry_id", 0)
                    pt = c.get("point", 1)
                    sketch.addConstraint(Sketcher.Constraint('Fixed', gid, pt))
                    constraint_count += 1
                    
                elif c_type == "symmetric":
                    id1 = c.get("id1", 0)
                    pt1 = c.get("point1", 1)
                    id2 = c.get("id2", 0)
                    pt2 = c.get("point2", 2)
                    axis = c.get("axis", "Y")
                    # -1 = X-axis, -2 = Y-axis
                    axis_id = -2 if axis.upper() == "Y" else -1
                    sketch.addConstraint(Sketcher.Constraint('Symmetric', id1, pt1, id2, pt2, axis_id))
                    constraint_count += 1
                    
                else:
                    FreeCAD.Console.PrintWarning(f"Unknown constraint type: '{c_type}'\n")
            
            doc.recompute()
            FreeCAD.Console.PrintMessage(
                f"Added {constraint_count} constraints to sketch '{sketch_name}'.\n"
            )
            return {"constraint_count": constraint_count, "message": f"Added {constraint_count} constraints"}
            
        except Exception as e:
            error_msg = f"Failed to add constraints: {str(e)}"
            FreeCAD.Console.PrintError(error_msg + "\n")
            return error_msg
    
    def create_extrusion(
        self,
        doc_name: str,
        name: str,
        sketch_name: str,
        length: float,
        symmetric: bool = False,
        reversed: bool = False,
        body_name: str = None
    ) -> dict[str, Any]:
        """Create an extrusion (Pad) from a sketch.
        
        Args:
            doc_name: Document name
            name: Name for the extrusion object
            sketch_name: Name of the sketch to extrude
            length: Extrusion length in mm
            symmetric: If True, extrude half in each direction
            reversed: If True, reverse extrusion direction
            body_name: Optional PartDesign Body name
        
        Returns:
            Success status and extrusion object name
        """
        rpc_request_queue.put(
            lambda: self._create_extrusion_gui(
                doc_name, name, sketch_name, length, symmetric, reversed, body_name
            )
        )
        res = rpc_response_queue.get()
        if isinstance(res, str):
            return {"success": False, "error": res}
        return {"success": True, "object_name": res["object_name"], "message": res["message"]}
    
    def _create_extrusion_gui(
        self,
        doc_name: str,
        name: str,
        sketch_name: str,
        length: float,
        symmetric: bool,
        reversed: bool,
        body_name: str
    ):
        """Create extrusion in GUI thread"""
        try:
            doc = FreeCAD.getDocument(doc_name)
            if not doc:
                return f"Document '{doc_name}' not found."
            
            sketch = doc.getObject(sketch_name)
            if not sketch:
                return f"Sketch '{sketch_name}' not found."
            
            # Get or find body
            body = None
            if body_name:
                body = doc.getObject(body_name)
            else:
                # Try to find the body that contains the sketch
                for obj in doc.Objects:
                    if obj.TypeId == 'PartDesign::Body':
                        if hasattr(obj, 'Group') and sketch in obj.Group:
                            body = obj
                            break
            
            # Create Pad
            if body:
                pad = doc.addObject("PartDesign::Pad", name)
                body.addObject(pad)
            else:
                pad = doc.addObject("PartDesign::Pad", name)
            
            pad.Profile = sketch
            pad.Length = length
            pad.Reversed = reversed
            pad.Midplane = symmetric
            
            # Hide sketch after extrusion
            if hasattr(sketch, 'ViewObject') and sketch.ViewObject:
                sketch.ViewObject.Visibility = False
            
            doc.recompute()
            
            FreeCAD.Console.PrintMessage(
                f"Extrusion '{name}' created from sketch '{sketch_name}' (length={length}mm).\n"
            )
            return {
                "object_name": name,
                "message": f"Extrusion created with length {length}mm"
            }
            
        except Exception as e:
            error_msg = f"Failed to create extrusion: {str(e)}"
            FreeCAD.Console.PrintError(error_msg + "\n")
            return error_msg
    
    def create_2020_extrusion(
        self,
        doc_name: str,
        name: str,
        length: float,
        position: dict[str, float] = None,
        direction: str = "Z",
        color: list[float] = None,
        simplified: bool = True,
        profile_variant: str = "2020",
        sealed_rotation: int = 0
    ) -> dict[str, Any]:
        """Create a 2020 aluminum extrusion profile.
        
        Args:
            doc_name: Document name
            name: Object name
            length: Extrusion length in mm
            position: Optional position {x, y, z}
            direction: Extrusion axis - "X", "Y", or "Z"
            color: Optional RGBA color [R, G, B, A]
            simplified: If True, use simple 20x20 box (fast). If False, create T-slot profile.
            profile_variant: Profile type - "2020" (4 slots), "2020N1" (3 slots),
                            "2020N2" (2 adjacent slots), "2020N3" (1 slot)
            sealed_rotation: Rotation of sealed faces in 90° increments (0, 90, 180, 270)
                            For 2020N1: which face is sealed
                            For 2020N2: which corner has the 2 sealed faces
                            For 2020N3: which face has the slot
        
        Returns:
            Success status and object name
        """
        rpc_request_queue.put(
            lambda: self._create_2020_extrusion_gui(
                doc_name, name, length, position, direction, color, simplified,
                profile_variant, sealed_rotation
            )
        )
        res = rpc_response_queue.get()
        if isinstance(res, str):
            return {"success": False, "error": res}
        return {"success": True, "object_name": res["object_name"], "message": res["message"]}
    
    def _create_2020_extrusion_gui(
        self,
        doc_name: str,
        name: str,
        length: float,
        position: dict[str, float],
        direction: str,
        color: list[float],
        simplified: bool,
        profile_variant: str = "2020",
        sealed_rotation: int = 0
    ):
        """Create 2020 extrusion in GUI thread"""
        try:
            import Part
            
            doc = FreeCAD.getDocument(doc_name)
            if not doc:
                return f"Document '{doc_name}' not found."
            
            pos_x = position.get("x", 0) if position else 0
            pos_y = position.get("y", 0) if position else 0
            pos_z = position.get("z", 0) if position else 0
            
            # Normalize profile variant
            variant = profile_variant.upper().replace("-", "")
            
            if simplified:
                # Create simple 20x20mm box
                if direction.upper() == "Z":
                    obj = doc.addObject("Part::Box", name)
                    obj.Length = 20
                    obj.Width = 20
                    obj.Height = length
                    # Center the profile
                    obj.Placement.Base = FreeCAD.Vector(pos_x - 10, pos_y - 10, pos_z)
                elif direction.upper() == "Y":
                    obj = doc.addObject("Part::Box", name)
                    obj.Length = 20
                    obj.Width = length
                    obj.Height = 20
                    obj.Placement.Base = FreeCAD.Vector(pos_x - 10, pos_y, pos_z - 10)
                elif direction.upper() == "X":
                    obj = doc.addObject("Part::Box", name)
                    obj.Length = length
                    obj.Width = 20
                    obj.Height = 20
                    obj.Placement.Base = FreeCAD.Vector(pos_x, pos_y - 10, pos_z - 10)
                else:
                    return f"Invalid direction '{direction}'. Use 'X', 'Y', or 'Z'."
            else:
                # Create detailed T-slot profile based on variant
                # 2020 profile dimensions (from 2020N2 spec):
                # - 20x20mm outer
                # - 6.1mm slot opening
                # - 11mm T-track width
                # - 5mm center bore
                # - 1.5mm corner radius
                size = 20.0
                half = size / 2.0
                slot_opening = 6.1  # Slot opening width
                slot_depth = 1.8    # Depth to T-track
                track_width = 11.0  # Internal T-track width
                track_depth = 6.0   # Total slot depth from surface
                bore_r = 2.5        # Center bore radius
                corner_r = 1.5      # Corner radius
                wall_t = 1.5        # Wall thickness
                
                # Determine which sides have slots based on variant
                # Sides: 0=bottom (-Y), 1=right (+X), 2=top (+Y), 3=left (-X)
                if variant == "2020":
                    slot_sides = [0, 1, 2, 3]  # All 4 sides have slots
                elif variant == "2020N1":
                    # 1 sealed, 3 slots - sealed side rotated by sealed_rotation
                    sealed_side = (sealed_rotation // 90) % 4
                    slot_sides = [s for s in [0, 1, 2, 3] if s != sealed_side]
                elif variant == "2020N2":
                    # 2 adjacent sealed, 2 slots - forms a corner
                    base = (sealed_rotation // 90) % 4
                    sealed_sides = [base, (base + 1) % 4]
                    slot_sides = [s for s in [0, 1, 2, 3] if s not in sealed_sides]
                elif variant == "2020N3":
                    # 3 sealed, 1 slot - only one side has slot
                    slot_side = (sealed_rotation // 90) % 4
                    slot_sides = [slot_side]
                else:
                    # Default to full 2020
                    slot_sides = [0, 1, 2, 3]
                
                # Build the profile as a 2D wire then extrude
                # Start with outer square and add T-slot cutouts
                from math import sqrt
                
                # Create outer square profile
                outer_wire = Part.makePolygon([
                    FreeCAD.Vector(-half, -half, 0),
                    FreeCAD.Vector(half, -half, 0),
                    FreeCAD.Vector(half, half, 0),
                    FreeCAD.Vector(-half, half, 0),
                    FreeCAD.Vector(-half, -half, 0)
                ])
                outer_face = Part.Face(outer_wire)
                
                # Extrude the outer shape
                solid = outer_face.extrude(FreeCAD.Vector(0, 0, length))
                
                # Cut center bore
                bore = Part.makeCylinder(bore_r, length)
                solid = solid.cut(bore)
                
                # Cut T-slots on active sides
                slot_half = slot_opening / 2.0
                track_half = track_width / 2.0
                
                for side in slot_sides:
                    # Create T-slot cutout shape
                    # T-slot: narrow opening, wider track inside
                    if side == 0:  # Bottom (-Y)
                        # Slot opening
                        slot_box = Part.makeBox(
                            slot_opening, slot_depth, length,
                            FreeCAD.Vector(-slot_half, -half, 0)
                        )
                        # T-track (wider part inside)
                        track_box = Part.makeBox(
                            track_width, track_depth - slot_depth, length,
                            FreeCAD.Vector(-track_half, -half + slot_depth, 0)
                        )
                        solid = solid.cut(slot_box)
                        solid = solid.cut(track_box)
                    elif side == 1:  # Right (+X)
                        slot_box = Part.makeBox(
                            slot_depth, slot_opening, length,
                            FreeCAD.Vector(half - slot_depth, -slot_half, 0)
                        )
                        track_box = Part.makeBox(
                            track_depth - slot_depth, track_width, length,
                            FreeCAD.Vector(half - track_depth, -track_half, 0)
                        )
                        solid = solid.cut(slot_box)
                        solid = solid.cut(track_box)
                    elif side == 2:  # Top (+Y)
                        slot_box = Part.makeBox(
                            slot_opening, slot_depth, length,
                            FreeCAD.Vector(-slot_half, half - slot_depth, 0)
                        )
                        track_box = Part.makeBox(
                            track_width, track_depth - slot_depth, length,
                            FreeCAD.Vector(-track_half, half - track_depth, 0)
                        )
                        solid = solid.cut(slot_box)
                        solid = solid.cut(track_box)
                    elif side == 3:  # Left (-X)
                        slot_box = Part.makeBox(
                            slot_depth, slot_opening, length,
                            FreeCAD.Vector(-half, -slot_half, 0)
                        )
                        track_box = Part.makeBox(
                            track_depth - slot_depth, track_width, length,
                            FreeCAD.Vector(-half, -track_half, 0)
                        )
                        solid = solid.cut(slot_box)
                        solid = solid.cut(track_box)
                
                # Create Part::Feature
                obj = doc.addObject("Part::Feature", name)
                obj.Shape = solid
                
                # Set placement and rotation based on direction
                if direction.upper() == "Z":
                    obj.Placement.Base = FreeCAD.Vector(pos_x, pos_y, pos_z)
                elif direction.upper() == "Y":
                    obj.Placement = FreeCAD.Placement(
                        FreeCAD.Vector(pos_x, pos_y, pos_z),
                        FreeCAD.Rotation(FreeCAD.Vector(1, 0, 0), 90)
                    )
                elif direction.upper() == "X":
                    obj.Placement = FreeCAD.Placement(
                        FreeCAD.Vector(pos_x, pos_y, pos_z),
                        FreeCAD.Rotation(FreeCAD.Vector(0, 1, 0), -90)
                    )
            
            # Apply color
            if color and hasattr(obj, 'ViewObject') and obj.ViewObject:
                obj.ViewObject.ShapeColor = tuple(color[:4] if len(color) >= 4 else color + [1.0])
            elif hasattr(obj, 'ViewObject') and obj.ViewObject:
                # Default aluminum gray
                obj.ViewObject.ShapeColor = (0.7, 0.7, 0.75, 1.0)
            
            # Ensure visibility
            if hasattr(obj, 'ViewObject') and obj.ViewObject:
                obj.ViewObject.Visibility = True
            
            doc.recompute()
            
            FreeCAD.Console.PrintMessage(
                f"2020 extrusion '{name}' created (length={length}mm, direction={direction}).\n"
            )
            return {
                "object_name": name,
                "message": f"2020 extrusion created ({length}mm along {direction} axis)"
            }
            
        except Exception as e:
            error_msg = f"Failed to create 2020 extrusion: {str(e)}"
            FreeCAD.Console.PrintError(error_msg + "\n")
            return error_msg
    
    def batch_position(
        self,
        doc_name: str,
        objects: list[str],
        offset: dict[str, float] = None,
        position: dict[str, float] = None,
        absolute: bool = False
    ) -> dict[str, Any]:
        """Update positions of multiple objects at once.
        
        Args:
            doc_name: Document name
            objects: List of object names to reposition
            offset: Relative offset to apply {x, y, z} - used when absolute=False
            position: Absolute position to set {x, y, z} - used when absolute=True
            absolute: If True, set absolute position. If False, apply relative offset.
        
        Returns:
            Success status and update count
        """
        rpc_request_queue.put(
            lambda: self._batch_position_gui(doc_name, objects, offset, position, absolute)
        )
        res = rpc_response_queue.get()
        if isinstance(res, str):
            return {"success": False, "error": res}
        return {"success": True, "updated_count": res["updated_count"], "message": res["message"]}
    
    def _batch_position_gui(
        self,
        doc_name: str,
        objects: list[str],
        offset: dict[str, float],
        position: dict[str, float],
        absolute: bool
    ):
        """Batch update positions in GUI thread"""
        try:
            doc = FreeCAD.getDocument(doc_name)
            if not doc:
                return f"Document '{doc_name}' not found."
            
            updated_count = 0
            not_found = []
            
            for obj_name in objects:
                obj = doc.getObject(obj_name)
                if not obj:
                    not_found.append(obj_name)
                    continue
                
                if not hasattr(obj, 'Placement'):
                    FreeCAD.Console.PrintWarning(
                        f"Object '{obj_name}' has no Placement property, skipping.\n"
                    )
                    continue
                
                current = obj.Placement.Base
                
                if absolute and position:
                    # Set absolute position
                    new_pos = FreeCAD.Vector(
                        position.get("x", current.x),
                        position.get("y", current.y),
                        position.get("z", current.z)
                    )
                elif offset:
                    # Apply relative offset
                    new_pos = FreeCAD.Vector(
                        current.x + offset.get("x", 0),
                        current.y + offset.get("y", 0),
                        current.z + offset.get("z", 0)
                    )
                else:
                    continue
                
                # Preserve rotation
                obj.Placement = FreeCAD.Placement(
                    new_pos,
                    obj.Placement.Rotation
                )
                updated_count += 1
            
            doc.recompute()
            
            msg = f"Updated {updated_count} of {len(objects)} objects"
            if not_found:
                msg += f". Not found: {', '.join(not_found)}"
            
            FreeCAD.Console.PrintMessage(msg + "\n")
            return {"updated_count": updated_count, "message": msg}
            
        except Exception as e:
            error_msg = f"Failed to batch update positions: {str(e)}"
            FreeCAD.Console.PrintError(error_msg + "\n")
            return error_msg

    def _save_active_screenshot(self, save_path: str, view_name: str = "Isometric"):
        try:
            view = FreeCADGui.ActiveDocument.ActiveView
            # Check if the view supports screenshots
            if not hasattr(view, 'saveImage'):
                return "Current view does not support screenshots"

            if view_name == "Isometric":
                view.viewIsometric()
            elif view_name == "Front":
                view.viewFront()
            elif view_name == "Top":
                view.viewTop()
            elif view_name == "Right":
                view.viewRight()
            elif view_name == "Back":
                view.viewBack()
            elif view_name == "Left":
                view.viewLeft()
            elif view_name == "Bottom":
                view.viewBottom()
            elif view_name == "Dimetric":
                view.viewDimetric()
            elif view_name == "Trimetric":
                view.viewTrimetric()
            else:
                raise ValueError(f"Invalid view name: {view_name}")
            view.fitAll()
            view.saveImage(save_path, 1)
            return True
        except Exception as e:
            return str(e)


def start_rpc_server(host="localhost", port=9875):
    global rpc_server_thread, rpc_server_instance

    if rpc_server_instance:
        return "RPC Server already running."

    rpc_server_instance = SimpleXMLRPCServer(
        (host, port), allow_none=True, logRequests=False
    )
    rpc_server_instance.register_instance(FreeCADRPC())

    def server_loop():
        FreeCAD.Console.PrintMessage(f"RPC Server started at {host}:{port}\n")
        rpc_server_instance.serve_forever()

    rpc_server_thread = threading.Thread(target=server_loop, daemon=True)
    rpc_server_thread.start()

    QtCore.QTimer.singleShot(500, process_gui_tasks)

    return f"RPC Server started at {host}:{port}."


def stop_rpc_server():
    global rpc_server_instance, rpc_server_thread

    if rpc_server_instance:
        rpc_server_instance.shutdown()
        rpc_server_thread.join()
        rpc_server_instance = None
        rpc_server_thread = None
        FreeCAD.Console.PrintMessage("RPC Server stopped.\n")
        return "RPC Server stopped."

    return "RPC Server was not running."


class StartRPCServerCommand:
    def GetResources(self):
        return {"MenuText": "Start RPC Server", "ToolTip": "Start RPC Server"}

    def Activated(self):
        msg = start_rpc_server()
        FreeCAD.Console.PrintMessage(msg + "\n")

    def IsActive(self):
        return True


class StopRPCServerCommand:
    def GetResources(self):
        return {"MenuText": "Stop RPC Server", "ToolTip": "Stop RPC Server"}

    def Activated(self):
        msg = stop_rpc_server()
        FreeCAD.Console.PrintMessage(msg + "\n")

    def IsActive(self):
        return True


FreeCADGui.addCommand("Start_RPC_Server", StartRPCServerCommand())
FreeCADGui.addCommand("Stop_RPC_Server", StopRPCServerCommand())