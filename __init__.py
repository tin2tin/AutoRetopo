# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTIBILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.

bl_info = {
    "name" : "Autoretopo",
    "author" : "Sphinx, tintwotin",
    "description" : "",
    "blender" : (5, 2, 0),
    "version" : (0, 0, 1),
    "location" : "view3D",
    "warning" : "",
    "category" : "Object"
}


import bpy
from bpy.props import *

from . SPX_op import SPX_OT_Apply_All_Op
from . SPX_panel import SPX_PT_Panel

#Scene properties

bpy.types.Scene.voxel_size = bpy.props.FloatProperty(
    name="Voxel Detail",
    description="Voxel remesh detail, as a fraction of the object's bounding box diagonal. Lower values preserve finer detail (more voxels, better at keeping thin gaps like between legs or fingers separate, and more faithful to the source proportions/silhouette) but are more likely to produce geometry Quadriflow rejects, falling back to a triangulated Decimate result; higher values are coarser (can round off thin gaps, reading as stockier/bulkier) but remesh to clean quads more reliably. Scales automatically with object size",
    default=0.005,
    min=0.0005,
    max=0.2,
    precision=4
)

bpy.types.Scene.pre_smooth_iterations = bpy.props.IntProperty(
    name="Pre-Smooth",
    description="Smooth the source mesh this many times before remeshing, to suppress small-scale noise (e.g. messy scan hair, self-intersecting debris) that would otherwise get faithfully voxelized into chaotic, shard-like geometry. 0 disables. Dense scans (millions of vertices) often need much higher values (50-150+) before any effect is visible, since each pass only moves a vertex a small fraction of its distance to its neighbors. Pushed too high, it will shrink and eventually collapse real detail (nose, coat folds) along with the noise - increase gradually and check the result",
    default=0,
    min=0,
    max=300
)

bpy.types.Scene.quad_enabled = bpy.props.BoolProperty(
    name="Quad faces",
    description="Enable quad remeshing",
    default=True
)

bpy.types.Scene.face_number = bpy.props.IntProperty(
    name="Faces",
    description="Target face count for quad remeshing, or for the Decimate fallback if Quadriflow rejects the mesh",
    default=1000,
    min=1,
    max=1000000
)

bpy.types.Scene.diffuse_texture = bpy.props.BoolProperty(
    name="Diffuse",
    description="",
    default=True
)

bpy.types.Scene.normal_texture = bpy.props.BoolProperty(
    name="Normal",
    description="",
    default=True
)

bpy.types.Scene.tex_size = bpy.props.IntProperty(
    name="Texture Size",
    description="Texture size",
    default=2048,
    min=1,
    max=50000
)

bpy.types.Scene.bakeFolder = bpy.props.StringProperty(
    name="",
    description="Choose a directory to save the output file",
    default="Output path",
    maxlen=1023,
    subtype='DIR_PATH'
)

# Progress reporting for the Apply Remesh operator, shown as a progress
# bar/status line under the button while it runs.
bpy.types.Scene.retopo_progress = bpy.props.FloatProperty(
    name="Progress",
    description="Progress of the current/last remesh operation",
    subtype='FACTOR',
    default=0.0,
    min=0.0,
    max=1.0
)

bpy.types.Scene.retopo_status = bpy.props.StringProperty(
    name="Status",
    description="What the remesh operator is currently doing",
    default=""
)



classes = (SPX_OT_Apply_All_Op, SPX_PT_Panel)

def register():
    for c in classes:
        bpy.utils.register_class(c)

def unregister():
    for c in classes:
        bpy.utils.unregister_class(c)

if __name__ == "__main__":
    register()