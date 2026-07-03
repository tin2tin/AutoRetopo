import bpy

from bpy.types import Panel

class SPX_PT_Panel(Panel):
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_label = "Auto Retopology"
    bl_category = "AutoRetopo"

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        col_title = layout.column(align=True)

         # Header for Remeshing
        row = col_title.row(align = True)
        row.label(text="Remeshing")


        box = layout.box()
        col = box.column(align=True)
        col.separator()
        
        # Voxel Size input
        row = col.row(align = True)
        row.prop(scene, "voxel_size")

        col.separator()

        # Pre-Smooth input
        row = col.row(align = True)
        row.prop(scene, "pre_smooth_iterations")

        col.separator()

        # Quad Enabled checkbox
        row = col.row(align = True)
        row.prop(scene, "quad_enabled")

        col.separator()

        if scene.quad_enabled:
            row = col.row(align = True)
            row.prop(scene, "face_number")

       

        
       

        
        # Header for textures
        col_title = layout.column(align=True)
        row = col_title.row(align = True)
        row.label(text="New Textures")


        box = layout.box()
        col = box.column(align=True)

        col.separator()

        # Diffuse Checkbox
        row = col.row(align = True)
        row.prop(scene, "diffuse_texture")

        col.separator()
        
        # Normal Checkbox
        row = col.row(align = True)
        row.prop(scene, "normal_texture")

        col.separator()

        # Diffuse Checkbox
        row = col.row(align = True)
        row.prop(scene, "tex_size")

        col.separator()


        #Path
        row = col.row(align = True)
        row.prop(scene, 'bakeFolder', text="")

        col.separator()

        

        row = col.row(align = True)
        col.separator()

        # Apply Remesh
        row.operator("object.vrt_remesh_op", icon='MOD_REMESH', text="Apply Remesh")

        # Progress bar + current-step status, shown while (and after) the
        # operator runs.
        if scene.retopo_status:
            col.separator()
            row = col.row(align=True)
            row.enabled = False
            row.prop(scene, "retopo_progress", text=scene.retopo_status, slider=True)
