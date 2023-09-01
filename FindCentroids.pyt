# -*- coding: utf-8 -*-

"""
Finds centroids from polygons grouped by a field.

Copyright (c) 2023 Dalhousie University

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

__author__ = "Thomas Zuberbuehler"
__date__ = "August 2023"
__copyright__ = "(c) 2023 Dalhousie University"

import arcpy, arcpy.da, arcpy.management

from collections.abc import Generator
from typing import List, Union, Tuple

import uuid
from collections import namedtuple
from contextlib import contextmanager

from pathlib import Path


# from aputil.use_memory context manager
# https://github.com/moosetraveller/aputil
@contextmanager
def use_memory() -> Generator[str, None, None]:

    name = rf"memory\fc_{uuid.uuid4().hex}"

    try:
        yield name
    finally:
        arcpy.management.Delete(name)


# from aputil.toolbox.ToolParameters
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
    
    def get_boolean(self, name: str) -> Union[bool, None]:
        parameter = self.parameters[name]
        if parameter:
            return parameter.value or parameter.value == "True"
        return None
    
    def clear_messages(self) -> None:
        for param in self.parameters.values():
            param.clearMessage()


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

        ignore_null_values = arcpy.Parameter(
            name="ignore_null_values",
            displayName="Ignore Null Values",
            datatype="GPBoolean",
            direction="Input",
            parameterType="Required",
        )

        ignore_null_values.value = True

        output_feature_class = arcpy.Parameter(
            name="output_feature_class",
            displayName="Output Point Feature Class",
            datatype="DEFeatureClass",
            direction="Output",
            parameterType="Required",
        )

        return [input_feature_class, input_feature_class_field, ignore_null_values, output_feature_class]

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
        ignore_null_values = params.get_boolean("ignore_null_values")

        output_name = Path(output_feature_class).name
        output_path = str(Path(output_feature_class).parent)
        spatial_reference = arcpy.Describe(input_feature_class).spatialReference

        arcpy.management.CreateFeatureclass(output_path, output_name, "Point", spatial_reference=spatial_reference)
        field: arcpy.Field = arcpy.ListFields(input_feature_class, group_field)[0]
        add_field_to(output_feature_class, field, True)

        with arcpy.da.SearchCursor(input_feature_class, [group_field]) as cursor:
            unique_values = set(record[0] for record in cursor if record[0] or not ignore_null_values)

        with arcpy.da.InsertCursor(output_feature_class, ["SHAPE@", group_field]) as input_cursor:

            for value in unique_values:

                field = arcpy.AddFieldDelimiters(input_feature_class, group_field)

                with use_memory() as selection, use_memory() as convex_hull:

                    if value:
                    
                        if isinstance(value, (float, int, bool)):
                            where_clause = f"{field} = {value}"
                        else:
                            where_clause = f"{field} = '{value}'"

                    elif not ignore_null_values:

                        where_clause = f"{field} IS Null"
                    
                    else:
                        continue
                
                    arcpy.AddMessage(where_clause)

                    arcpy.management.MakeFeatureLayer(input_feature_class, selection, where_clause)
                    arcpy.management.MinimumBoundingGeometry(selection, convex_hull, "CONVEX_HULL", "ALL")

                    with arcpy.da.SearchCursor(convex_hull, "SHAPE@") as cursor:
                        polygon: arcpy.Polygon = next(cursor)[0]
                        centroid: arcpy.Point = polygon.trueCentroid
                        input_cursor.insertRow([centroid, value])

        return output_feature_class

    def postExecute(self, parameters):
        
        return