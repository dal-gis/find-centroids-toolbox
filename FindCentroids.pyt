# -*- coding: utf-8 -*-

"""
Finds centroids from polygons grouped by a field.

:author:
    Thomas Zuberbuehler (Dalhousie University)
"""

# -*- coding: utf-8 -*-

import arcpy, arcpy.da, arcpy.management

from collections.abc import Generator
from typing import List, Union, Tuple

import uuid
from collections import namedtuple
from contextlib import contextmanager

from pathlib import Path


# aputil.use_memory context manager
# https://github.com/moosetraveller/aputil
@contextmanager
def use_memory() -> Generator[str, None, None]:

    name = rf"memory\fc_{uuid.uuid4().hex}"

    try:
        yield name
    finally:
        arcpy.management.Delete(name)

# aputil.toolbox.ToolParameters
# https://github.com/moosetraveller/aputil
class ToolParameters:

    def __init__(self, parameters: List[arcpy.Parameter]):
        self.parameters = {p.name: p for p in parameters}
    
    def __iter__(self):
        self.iterator = iter(self.parameters.items())
        return self
    
    def __next__(self):
        return next(self.iterator)
    
    def get_string(self, name: str) -> Union[str, None]:
        parameter = self.parameters[name]
        if parameter:
            return parameter.valueAsText
        return None
    
    def clear_messages(self) -> None:
        for param in self.parameters.values():
            param.clearMessage()

def __replace_shape_field_name(field_name: str) -> str:

    if "SHAPE@" == field_name:
        return "SHAPE"
    if "SHAPE@" in field_name:
        return field_name.replace("@", "_")
    
    return field_name

# aputil.tcursor
# https://github.com/moosetraveller/aputil
def tcursor(cursor: arcpy.da.SearchCursor) -> Generator[Tuple, None, None]:

    fields = map(__replace_shape_field_name, cursor.fields)

    tcursor_tuple = namedtuple(f"tcursor_{uuid.uuid4().hex}", fields)

    for row in cursor:
        yield tcursor_tuple(*row)


def add_field_to(feature_class: str, template: arcpy.Field, required: bool = False):

    arcpy.management.AddField(
        feature_class, 
        template.name, 
        template.type, 
        template.precision, 
        template.scale, 
        template.length, 
        template.aliasName, 
        template.isNullable, 
        required,
        template.domain
    )


class Toolbox(object):

    def __init__(self):

        self.label = "Find Centroids Toolbox"
        self.alias = "FindCentroid"

        # List of tool classes associated with this toolbox
        self.tools = [FindCentroidsTool]


class FindCentroidsTool(object):

    def __init__(self):
        
        self.label = "Find Centroids"
        self.description = "Finds centroids from polygons grouped by a field."
        self.canRunInBackground = False

    def getParameterInfo(self) -> List[arcpy.Parameter]:

        input_feature_class = arcpy.Parameter(
            name="input_feature_class",
            displayName="Polygon Feature Class",
            datatype="DEFeatureClass",
            direction="Input",
            parameterType="Required",
        )

        input_feature_class.filter.list = ["Polygon"]

        input_feature_class_field = arcpy.Parameter(
            name="group_field",
            displayName="Group Field",
            datatype="Field",
            direction="Input",
            parameterType="Required",
        )

        input_feature_class_field.parameterDependencies = [input_feature_class.name]

        output_feature_class = arcpy.Parameter(
            name="output_feature_class",
            displayName="Output Point Feature Class",
            datatype="DEFeatureClass",
            direction="Output",
            parameterType="Required",
        )

        return [input_feature_class, input_feature_class_field, output_feature_class]

    def isLicensed(self):
        return True

    def updateParameters(self, parameters):
        
        return

    def updateMessages(self, parameters):
        
        return

    def execute(self, parameters: List[arcpy.Parameter], _):
        
        params = ToolParameters(parameters)
        params.clear_messages()

        input_feature_class = params.get_string("input_feature_class")
        group_field = params.get_string("group_field")
        output_feature_class = params.get_string("output_feature_class")

        output_name = Path(output_feature_class).name
        output_path = str(Path(output_feature_class).parent)
        spatial_reference = arcpy.Describe(input_feature_class).spatialReference

        arcpy.management.CreateFeatureclass(output_path, output_name, "Point", spatial_reference=spatial_reference)
        field: arcpy.Field = arcpy.ListFields(input_feature_class, group_field)[0]
        add_field_to(output_feature_class, field, True)

        with arcpy.da.SearchCursor(input_feature_class, [group_field]) as cursor:
            unique_values = set(record[0] for record in cursor if record[0])

        with arcpy.da.InsertCursor(output_feature_class, ["SHAPE@", group_field]) as input_cursor:

            for value in unique_values:

                field = arcpy.AddFieldDelimiters(input_feature_class, group_field)

                with use_memory() as selection, use_memory() as convex_hull:
                
                    arcpy.AddMessage(f"{field} = '{value}'")
                    arcpy.management.MakeFeatureLayer(input_feature_class, selection, f"{field} = '{value}'")
                    arcpy.management.MinimumBoundingGeometry(selection, convex_hull, "CONVEX_HULL", "ALL")

                    with arcpy.da.SearchCursor(convex_hull, "SHAPE@") as cursor:
                        polygon: arcpy.Polygon = next(tcursor(cursor)).SHAPE
                        centroid: arcpy.Point = polygon.trueCentroid
                        input_cursor.insertRow([centroid, value])

        return output_feature_class

    def postExecute(self, parameters):
        
        return