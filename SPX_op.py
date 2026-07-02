import bpy
import os

from bpy.types import Operator

class SPX_OT_Apply_All_Op(Operator):
    bl_idname = "object.vrt_remesh_op"
    bl_label = "Apply all" #redundant?
    bl_description = "Apply all modifiers on the active object"
    bl_options = {'REGISTER', 'UNDO'}

    
    @classmethod
    def poll(cls, context):  
        return len(context.selected_objects) > 0
    
    
    def execute(self, context):
        
        scene = context.scene
        voxel_size = scene.voxel_size
        quad_enabled = scene.quad_enabled
        face_number = scene.face_number
        diffuse_enabled = scene.diffuse_texture
        normal_enabled = scene.normal_texture
        tex_size = scene.tex_size
        bakeFolder = scene.bakeFolder

        bpy.context.space_data.overlay.show_stats = True
        bpy.context.scene.render.engine = 'CYCLES'

        #test folder
        hasfolder = os.access(bakeFolder, os.W_OK)
        if hasfolder is False:
            self.report({'WARNING'}, "Select a valid export folder!")
            return {'FINISHED'}
        
        if context.active_object and context.active_object.type == 'MESH':
            #save OG object
            bpy.ops.object.shade_smooth()
            original_obj = context.active_object
            original_obj_name = original_obj.name

            try:
                #create a duplicate, it will be auto selected
                bpy.ops.object.duplicate_move(OBJECT_OT_duplicate={"linked":False, "mode":'TRANSLATION'}, TRANSFORM_OT_translate={"value":(0, 0, 0), "orient_type":'GLOBAL', "orient_matrix":((0, 0, 0), (0, 0, 0), (0, 0, 0)), "orient_matrix_type":'GLOBAL', "constraint_axis":(False, False, False), "mirror":False, "use_proportional_edit":False, "proportional_edit_falloff":'SMOOTH', "proportional_size":1, "use_proportional_connected":False, "use_proportional_projected":False, "snap":False, "snap_elements":{'INCREMENT'}, "use_snap_project":False, "snap_target":'CLOSEST', "use_snap_self":True, "use_snap_edit":True, "use_snap_nonedit":True, "use_snap_selectable":False, "snap_point":(0, 0, 0), "snap_align":False, "snap_normal":(0, 0, 0), "gpencil_strokes":False, "cursor_transform":False, "texture_space":False, "remove_on_cancel":False, "use_duplicated_keyframes":False, "view2d_edge_pan":False, "release_confirm":False, "use_accurate":False, "use_automerge_and_split":False})
                new_object = context.active_object
                new_object_name = new_object.name
                # bpy.context.view_layer.objects.active = obj
                # Apply Voxel Remesh Modifier
                if voxel_size > 0:
                    bpy.context.object.data.remesh_voxel_size = voxel_size
                    bpy.ops.object.voxel_remesh()

                    # Additionally, apply quad remeshing
                    if quad_enabled:
                        bpy.ops.object.quadriflow_remesh(target_faces=face_number)

                # add modifiers
                bpy.ops.object.modifier_add(type='MULTIRES')
                bpy.ops.object.modifier_add(type='SHRINKWRAP')

                #Shrinkwrap settings
                bpy.context.object.modifiers["Shrinkwrap"].wrap_method = 'PROJECT'
                bpy.context.object.modifiers["Shrinkwrap"].use_negative_direction = True
                bpy.context.object.modifiers["Shrinkwrap"].target = original_obj

                bpy.ops.object.multires_subdivide(modifier="Multires", mode='CATMULL_CLARK')
                bpy.ops.object.multires_subdivide(modifier="Multires", mode='CATMULL_CLARK')
                bpy.ops.object.multires_subdivide(modifier="Multires", mode='CATMULL_CLARK')

                bpy.ops.object.modifier_apply(modifier="Shrinkwrap")
                bpy.context.object.modifiers["Multires"].levels = 0
                bpy.ops.object.shade_smooth()

                #UV unwrapping
                bpy.ops.object.mode_set(mode='EDIT')
                bpy.ops.mesh.select_all(action='SELECT')
                bpy.ops.uv.smart_project(scale_to_bounds=True)
                bpy.ops.object.mode_set(mode='OBJECT')

                # Creating the new material and textures
                material = bpy.data.materials.new(name=f"{bpy.ops.object.name}_Mat")
                material.use_nodes = True
                bsdf_node = material.node_tree.nodes.get('Principled BSDF')
                nodes = material.node_tree.nodes
                links = material.node_tree.links
                
                if bsdf_node:
                    # Create and assign diffuse texture
                    if diffuse_enabled:  
                        diffuse_image_name = f"{context.active_object.name}_Diffuse"
                        diffuse_image = bpy.data.images.new(name=diffuse_image_name, width=tex_size, height=tex_size, alpha=True)
                        diffuse_node = material.node_tree.nodes.new(type='ShaderNodeTexImage')
                        diffuse_node.image = diffuse_image
                        diffuse_node.location = (-400, 400)
                        
                    
                    # Create and assign normal texture
                    if normal_enabled:
                        normal_image_name = f"{context.active_object.name}_Normal"
                        normal_image = bpy.data.images.new(name=normal_image_name, width=tex_size, height=tex_size, alpha=False, float_buffer=True)
                        normal_texture_node = material.node_tree.nodes.new(type='ShaderNodeTexImage')
                        normal_texture_node.image = normal_image
                        normal_texture_node.interpolation = 'Closest'
                        normal_texture_node.location = (-400, 200)

                        #adding a normal mapping node
                        norm_map = material.node_tree.nodes.new('ShaderNodeNormalMap') 
                        norm_map.location = (-100,0)
                    
                    # if ao_enabled:  
                    #     ao_image_name = f"{context.active_object.name}_AO"
                    #     ao_image = bpy.data.images.new(name=ao_image_name, width=2048, height=2048, alpha=True)
                    #     ao_node = material.node_tree.nodes.new(type='ShaderNodeTexImage')
                    #     ao_node.image = ao_image
                    #     ao_node.location = (-400, 0)

                    #     #adding a multiply node
                    #     ao_mult = material.node_tree.nodes.new('Multiply') 
                    #     ao_mult.location = (-300,0)

                      
                        
                # Assign material to the active object
                if len(context.active_object.data.materials) > 0:
                    context.active_object.data.materials[0] = material
                else:
                    context.active_object.data.materials.append(material)


                #Baking time
                bpy.ops.object.select_all(action='DESELECT')  # Deselect all objects
                bpy.data.objects[original_obj_name].select_set(True)  # Select the original object
                bpy.data.objects[new_object_name].select_set(True)  # Select the new object (target)
                bpy.context.view_layer.objects.active = bpy.data.objects[new_object_name]

                #NORMAL
                bpy.context.scene.render.bake.use_multires = True
                bpy.context.scene.cycles.tile_size = 512
                bpy.context.scene.cycles.samples = 10

                for node in nodes:
                    node.select = False
                normal_texture_node.select = True
                nodes.active = normal_texture_node
                
                bpy.ops.object.bake(type='NORMAL', use_clear=True, normal_space='TANGENT')
                normal_image.filepath_raw = bakeFolder+normal_image_name+".png"
                normal_image.file_format = 'PNG'
                normal_image.save()

                #DIFFUSE
                bpy.context.scene.render.bake.use_multires = False
                bpy.context.scene.render.bake.use_pass_direct = False
                bpy.context.scene.render.bake.use_pass_indirect = False
                bpy.context.scene.render.bake.use_pass_color = True
                bpy.context.scene.render.bake.use_selected_to_active = True
                bpy.context.scene.render.bake.cage_extrusion = 0.15

                
                for node in nodes:
                    node.select = False
                diffuse_node.select = True
                nodes.active = diffuse_node
                
                bpy.ops.object.bake(type='DIFFUSE', use_clear=True, use_selected_to_active=True)
                diffuse_image.filepath_raw = bakeFolder+diffuse_image_name+".png"
                diffuse_image.file_format = 'PNG'
                diffuse_image.save()

                links.new(normal_texture_node.outputs['Color'], norm_map.inputs['Color'])
                links.new(norm_map.outputs['Normal'], bsdf_node.inputs['Normal'])
                links.new(bsdf_node.inputs['Base Color'], diffuse_node.outputs['Color'])

                   
            except Exception as e:
                # Report an error for any issues applying the modifier
                self.report({'ERROR'}, f"Error applying remesh to {original_obj_name}: {e}")
        else:
            self.report({'ERROR'}, f"Error applying remesh to {original_obj_name}: not context.active_object and context.active_object.type != 'MESH':")
                

        self.report({'INFO'}, "Remesh applied")
        return {'FINISHED'}
