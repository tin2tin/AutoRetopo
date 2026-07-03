import bpy
import os
import bmesh
import mathutils

from bpy.types import Operator


def _merge_small_islands(mesh, min_relative_size=0.05):
    """Pull connected face islands that are small relative to the
    largest island onto the main surface, instead of deleting them.
    Raw scans commonly contain disconnected debris (holes from
    occlusion, hair, thin fabric) that can be several faces large, so
    a simple "loose geometry" delete (which only catches single
    isolated faces/edges/verts) isn't enough to find them. Rather than
    discarding that geometry, snap each small island's vertices onto
    their nearest vertex on the main surface. This only repositions
    vertices - no vertices or faces are deleted or welded, so polygon
    count is fully preserved."""
    bm = bmesh.new()
    bm.from_mesh(mesh)
    bm.faces.ensure_lookup_table()
    bm.verts.ensure_lookup_table()

    visited = set()
    islands = []
    for seed in bm.faces:
        if seed.index in visited:
            continue
        stack = [seed]
        island = []
        while stack:
            f = stack.pop()
            if f.index in visited:
                continue
            visited.add(f.index)
            island.append(f)
            for e in f.edges:
                for linked_face in e.link_faces:
                    if linked_face.index not in visited:
                        stack.append(linked_face)
        islands.append(island)

    if len(islands) > 1:
        largest_island = max(islands, key=len)
        min_size = max(1, int(len(largest_island) * min_relative_size))
        small_islands = [island for island in islands if len(island) < min_size]

        if small_islands:
            main_verts_list = list({v for f in largest_island for v in f.verts})

            kd = mathutils.kdtree.KDTree(len(main_verts_list))
            for i, v in enumerate(main_verts_list):
                kd.insert(v.co, i)
            kd.balance()

            small_verts = {v for island in small_islands for f in island for v in f.verts}
            for v in small_verts:
                co, index, dist = kd.find(v.co)
                v.co = co

            bm.to_mesh(mesh)
            mesh.update()

    bm.free()


def _open_edge_fraction(mesh):
    """Fraction of edges not shared by exactly two faces, computed in
    O(1) from loop/edge totals (every loop contributes one face-use of
    one edge, so a fully closed 2-manifold has loops == 2 * edges).
    AI-generated meshes (TRELLIS etc.) are often clouds of hundreds of
    thousands of tiny disconnected open patches that only look like a
    continuous surface; this cheaply detects that pathology on
    multi-million-poly inputs where a bmesh scan would be slow."""
    if len(mesh.edges) == 0:
        return 0.0
    open_edges = max(0, 2 * len(mesh.edges) - len(mesh.loops))
    return open_edges / len(mesh.edges)


def _scale_mesh_verts(mesh, factor):
    """Uniformly scale mesh-data vertex coordinates about the origin.
    Used to work around a Blender Quadriflow limitation: it silently
    treats edges below roughly 0.01 absolute units as degenerate and
    rejects the whole mesh as "non-manifold", so small real-world-scale
    objects must be scaled up for the call and back down after."""
    coords = [0.0] * (len(mesh.vertices) * 3)
    mesh.vertices.foreach_get("co", coords)
    coords = [c * factor for c in coords]
    mesh.vertices.foreach_set("co", coords)
    mesh.update()


def _remove_tiny_shells(mesh, min_relative_size=0.01):
    """Remove tiny disconnected shells from a freshly *generated*
    (voxel-remeshed) mesh. Voxel-remeshing overlapping fragment-cloud
    input can leave small floating blobs trapped inside the body; they
    are remesh artifacts, not source geometry (the source object is
    never touched), and they waste face budget in every later step."""
    bm = bmesh.new()
    bm.from_mesh(mesh)
    bm.faces.ensure_lookup_table()

    visited = set()
    islands = []
    for seed in bm.faces:
        if seed.index in visited:
            continue
        stack = [seed]
        island = []
        while stack:
            f = stack.pop()
            if f.index in visited:
                continue
            visited.add(f.index)
            island.append(f)
            for e in f.edges:
                for lf in e.link_faces:
                    if lf.index not in visited:
                        stack.append(lf)
        islands.append(island)

    if len(islands) > 1:
        largest = max(len(i) for i in islands)
        min_size = max(1, int(largest * min_relative_size))
        doomed = [f for isl in islands if len(isl) < min_size for f in isl]
        if doomed:
            bmesh.ops.delete(bm, geom=doomed, context='FACES')
            bm.to_mesh(mesh)
            mesh.update()

    bm.free()


class SPX_OT_Apply_All_Op(Operator):
    bl_idname = "object.vrt_remesh_op"
    bl_label = "Apply all"
    bl_description = "Apply all modifiers on the active object"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return len(context.selected_objects) > 0

    def _report_progress(self, context, fraction, status):
        """Update the panel's progress bar/status text and force an
        immediate redraw. execute() runs as a single blocking call, so
        without forcing a redraw here the UI wouldn't visibly update
        until the whole operator finished."""
        context.scene.retopo_progress = fraction
        context.scene.retopo_status = status
        print(f"[AutoRetopo] {status} ({fraction * 100:.0f}%)")
        if context.window:
            for area in context.screen.areas:
                area.tag_redraw()
            try:
                bpy.ops.wm.redraw_timer(type='DRAW_WIN_SWAP', iterations=1)
            except Exception:
                pass

    def execute(self, context):
        scene = context.scene
        voxel_size = scene.voxel_size
        pre_smooth_iterations = scene.pre_smooth_iterations
        quad_enabled = scene.quad_enabled
        face_number = scene.face_number
        diffuse_enabled = scene.diffuse_texture
        normal_enabled = scene.normal_texture
        tex_size = scene.tex_size
        bakeFolder = scene.bakeFolder

        bpy.context.space_data.overlay.show_stats = True
        bpy.context.scene.render.engine = 'CYCLES'

        # Ensure the bake folder exists and is writable
        if not os.path.exists(bakeFolder) or not os.access(bakeFolder, os.W_OK):
            self.report({'WARNING'}, "Select a valid export folder!")
            return {'FINISHED'}
        
        # Ensure path ends with the proper directory separator
        if not bakeFolder.endswith(os.sep):
            bakeFolder += os.sep
        
        if context.active_object and context.active_object.type == 'MESH':
            self._report_progress(context, 0.0, "Preparing...")
            bpy.ops.object.shade_smooth()
            original_obj = context.active_object
            original_obj_name = original_obj.name

            try:
                # Create a duplicate of the original object
                bpy.ops.object.duplicate(linked=False)
                new_object = context.active_object
                new_object_name = new_object.name

                # Detect fragment-cloud geometry. AI-generated meshes
                # (TRELLIS and similar image-to-3D models) are often not a
                # continuous surface at all but hundreds of thousands of
                # tiny overlapping open patches - only *looking* solid
                # because the fragments tile the visible surface. Voxel
                # remesh turns the gaps between such zero-thickness
                # fragments into real holes ("swiss cheese"), and the
                # island-merge below is both meaningless and extremely slow
                # on that kind of input, so it is skipped in favor of
                # solidifying before the voxel step.
                self._report_progress(context, 0.08, "Analyzing mesh...")
                is_fragment_cloud = _open_edge_fraction(new_object.data) > 0.05

                if not is_fragment_cloud:
                    # Clean up raw scan data before remeshing. Scan meshes
                    # often contain small disconnected floating fragments
                    # (holes from occlusion, hair, thin fabric edges).
                    # Nothing is deleted here - small islands are only
                    # repositioned (see _merge_small_islands), never
                    # removed.
                    self._report_progress(context, 0.12, "Merging small islands...")
                    _merge_small_islands(new_object.data)

                # Optional pre-smooth, run before voxelizing. Voxel remesh
                # faithfully resolves whatever amplitude of noise is present
                # at its grid resolution, so a fine voxel size that's needed
                # to preserve real thin gaps (legs, fingers) will just as
                # faithfully turn chaotic scan noise (messy hair, overlapping
                # debris) into shattered, shard-like geometry. Smoothing first
                # damps that small-scale noise independently of voxel size.
                if pre_smooth_iterations > 0:
                    self._report_progress(context, 0.16, "Pre-smoothing...")
                    # Use the Smooth modifier (native code) rather than the
                    # mesh.vertices_smooth operator (Python, edit-mode). Its
                    # per-pass movement is bounded by local edge length, so
                    # on a dense multi-million-vertex scan the operator loop
                    # needs a huge iteration count to move points a visually
                    # meaningful distance - and running that many iterations
                    # through the operator is far too slow to be practical.
                    # The modifier does the same underlying algorithm but is
                    # orders of magnitude faster, making that iteration count
                    # actually reachable.
                    smooth_mod = new_object.modifiers.new(name="AutoRetopoPreSmooth", type='SMOOTH')
                    smooth_mod.factor = 0.5
                    smooth_mod.iterations = pre_smooth_iterations
                    bpy.ops.object.modifier_apply(modifier=smooth_mod.name)

                # Apply Voxel Remesh
                # voxel_size is a fraction of the bounding box diagonal, so the
                # actual voxel resolution scales with the object instead of
                # using a fixed absolute size that may be far too coarse (or
                # fine) depending on the object's real-world scale.
                if voxel_size > 0:
                    bbox_diagonal = new_object.dimensions.length
                    actual_voxel_size = max(bbox_diagonal * voxel_size, 0.0001)

                    # Fragment clouds (and any largely-open thin-shell
                    # geometry) must be given real thickness before voxel
                    # remeshing: with thickness comfortably above the voxel
                    # size, the overlapping fragment slabs union into one
                    # continuous solid instead of a shell full of holes
                    # wherever fragments meet. Verified on real TRELLIS
                    # output: genus drops from ~539 (riddled with holes)
                    # to ~3 (clean solid).
                    if is_fragment_cloud:
                        self._report_progress(context, 0.16, "Solidifying open surface...")
                        solid_mod = new_object.modifiers.new(name="AutoRetopoSolidify", type='SOLIDIFY')
                        solid_mod.thickness = actual_voxel_size * 2.0
                        solid_mod.offset = 0.0
                        bpy.ops.object.modifier_apply(modifier=solid_mod.name)

                    self._report_progress(context, 0.2, "Voxel remeshing...")
                    new_object.data.remesh_voxel_size = actual_voxel_size
                    bpy.ops.object.voxel_remesh()

                    # Drop tiny floating blobs the voxel remesh generated
                    # from isolated fragment clusters (artifacts of the
                    # *generated* mesh; the source object is untouched).
                    self._report_progress(context, 0.32, "Removing remesh artifacts...")
                    _remove_tiny_shells(new_object.data)

                    # Voxel remesh is supposed to always produce a clean,
                    # watertight manifold mesh, but on pathological input
                    # (extremely thin/noisy surfaces near the voxel grid's
                    # resolution limit) it can occasionally leave small
                    # non-manifold holes or inconsistent normals of its own.
                    # Quadriflow requires clean manifold input to run at
                    # all, so repair this *before* Quadriflow rather than
                    # after - patching it afterward was too late, since
                    # Quadriflow had already rejected the broken input and
                    # left the raw, much-higher-poly voxel result in place.
                    self._report_progress(context, 0.35, "Repairing mesh...")
                    bpy.ops.object.mode_set(mode='EDIT')
                    bpy.ops.mesh.select_all(action='SELECT')
                    bpy.ops.mesh.normals_make_consistent(inside=False)
                    bpy.ops.mesh.select_all(action='DESELECT')
                    bpy.ops.mesh.select_non_manifold()
                    bpy.ops.mesh.fill_holes(sides=0)

                    # fill_holes only patches genuine boundary gaps (edges
                    # with 1 linked face). It doesn't fix "extra" non-manifold
                    # edges (3+ linked faces), which typically come from a
                    # handful of near-duplicate/overlapping faces left by
                    # voxel remesh on pathological input. Merge just those
                    # remaining non-manifold vertices by distance to weld
                    # the duplicates, then recalculate normals once more
                    # since fill_holes' new faces can be backwards-facing.
                    bpy.ops.mesh.select_all(action='DESELECT')
                    bpy.ops.mesh.select_non_manifold()
                    bpy.ops.mesh.remove_doubles(threshold=0.0001, use_unselected=False)
                    bpy.ops.mesh.select_all(action='SELECT')
                    bpy.ops.mesh.normals_make_consistent(inside=False)
                    bpy.ops.object.mode_set(mode='OBJECT')

                    # Apply quad remeshing if enabled
                    if quad_enabled:
                        self._report_progress(context, 0.4, "Quad remeshing...")

                        # Blender's Quadriflow silently treats edges below
                        # roughly 0.01 absolute units as degenerate and
                        # rejects the whole mesh with a misleading
                        # "non-manifold" error. A 1-unit-tall character
                        # remeshed at fine voxel detail sits permanently
                        # below that threshold, so temporarily scale the
                        # mesh data up for the call and back down after.
                        # Verified on real TRELLIS output: identical mesh
                        # fails at 1x and produces clean quads at 10x.
                        quad_scale = max(1.0, 0.05 / actual_voxel_size)
                        if quad_scale > 1.0:
                            _scale_mesh_verts(new_object.data, quad_scale)

                        quad_result = bpy.ops.object.quadriflow_remesh(target_faces=face_number)

                        if quad_scale > 1.0:
                            _scale_mesh_verts(new_object.data, 1.0 / quad_scale)

                        if 'FINISHED' not in quad_result:
                            # Even with all of the above, Quadriflow can
                            # still reject certain topology - a robustness
                            # limitation of its field-based algorithm, not
                            # something further cleanup reliably fixes. Fall
                            # back to Decimate so the user still gets a
                            # low-poly result near their target face count,
                            # instead of the raw, much-higher-poly voxel mesh.
                            self._report_progress(context, 0.45, "Quad remeshing failed, decimating instead...")
                            current_faces = len(new_object.data.polygons)
                            if current_faces > face_number:
                                decimate_mod = new_object.modifiers.new(name="AutoRetopoFallbackDecimate", type='DECIMATE')
                                decimate_mod.ratio = face_number / current_faces
                                bpy.ops.object.modifier_apply(modifier=decimate_mod.name)
                            self.report({'WARNING'}, "Quad remeshing failed on this mesh (non-manifold or inconsistent normals); used Decimate instead to still reach roughly the requested face count, so the result is triangulated rather than quads")

                    # Final safety-net repair. Both Quadriflow and, more
                    # surprisingly, an aggressive Decimate fallback (millions
                    # of faces collapsed down to the target count is a very
                    # severe reduction ratio) can occasionally tear open
                    # small holes even when their input was clean. Catch
                    # whatever is left right before UV unwrapping/baking,
                    # since that's what actually shows up as see-through
                    # holes in the final result.
                    self._report_progress(context, 0.5, "Final hole check...")
                    bpy.ops.object.mode_set(mode='EDIT')
                    bpy.ops.mesh.select_all(action='DESELECT')
                    bpy.ops.mesh.select_non_manifold()
                    bpy.ops.mesh.fill_holes(sides=0)
                    bpy.ops.mesh.select_all(action='SELECT')
                    bpy.ops.mesh.normals_make_consistent(inside=False)
                    bpy.ops.object.mode_set(mode='OBJECT')

                bpy.ops.object.shade_smooth()

                # UV unwrapping the low-poly mesh
                self._report_progress(context, 0.55, "UV unwrapping...")
                bpy.ops.object.mode_set(mode='EDIT')
                bpy.ops.mesh.select_all(action='SELECT')
                bpy.ops.uv.smart_project(scale_to_bounds=True)
                bpy.ops.object.mode_set(mode='OBJECT')

                # Creating the new target material. Start from a copy of
                # the original mesh's material rather than a blank one, so
                # settings the bake doesn't cover (Roughness, Metallic,
                # Specular, Emission, any extra texture maps) carry over
                # instead of resetting to Blender's defaults. Base Color
                # and Normal get overridden below with the freshly baked
                # textures, since those need to match the new UV layout.
                self._report_progress(context, 0.6, "Setting up material...")
                original_material = original_obj.data.materials[0] if original_obj.data.materials else None
                if original_material:
                    material = original_material.copy()
                    material.name = f"{new_object_name}_Mat"
                    if not material.use_nodes:
                        material.use_nodes = True
                else:
                    material = bpy.data.materials.new(name=f"{new_object_name}_Mat")
                    material.use_nodes = True
                nodes = material.node_tree.nodes
                links = material.node_tree.links
                bsdf_node = next((n for n in nodes if n.type == 'BSDF_PRINCIPLED'), None)
                
                diffuse_node = None
                normal_texture_node = None
                norm_map = None

                # Setup nodes based on settings
                if bsdf_node:
                    if diffuse_enabled:  
                        diffuse_image_name = f"{new_object_name}_Diffuse"
                        diffuse_image = bpy.data.images.new(name=diffuse_image_name, width=tex_size, height=tex_size, alpha=True)
                        diffuse_node = nodes.new(type='ShaderNodeTexImage')
                        diffuse_node.image = diffuse_image
                        diffuse_node.location = (-400, 400)
                        
                    if normal_enabled:
                        normal_image_name = f"{new_object_name}_Normal"
                        normal_image = bpy.data.images.new(name=normal_image_name, width=tex_size, height=tex_size, alpha=False, float_buffer=True)
                        normal_image.colorspace_settings.name = 'Non-Color'
                        normal_texture_node = nodes.new(type='ShaderNodeTexImage')
                        normal_texture_node.image = normal_image
                        normal_texture_node.interpolation = 'Closest'
                        normal_texture_node.location = (-400, 200)

                        norm_map = nodes.new('ShaderNodeNormalMap') 
                        norm_map.location = (-100, 0)
                        
                # Assign the material to the low-poly object
                if len(new_object.data.materials) > 0:
                    new_object.data.materials[0] = material
                else:
                    new_object.data.materials.append(material)

                # Set up Selected-to-Active baking selections
                bpy.ops.object.select_all(action='DESELECT')
                bpy.data.objects[original_obj_name].select_set(True)  # Select source high-poly (Selected)
                bpy.data.objects[new_object_name].select_set(True)     # Select target low-poly (Active)
                bpy.context.view_layer.objects.active = bpy.data.objects[new_object_name]

                # Common Bake Engine Settings
                bpy.context.scene.render.bake.use_multires = False
                bpy.context.scene.cycles.tile_size = 512
                bpy.context.scene.cycles.samples = 10

                # Cage extrusion must scale with the object: a fixed 0.15
                # units is 15% of body height on a 1-unit-tall character,
                # making bake rays from the chest reach the back and bleed
                # texture across unrelated surfaces. 2% of the bounding box
                # diagonal comfortably covers the low/high-poly surface
                # distance at any object scale.
                bake_cage_extrusion = new_object.dimensions.length * 0.02

                # Bake Normal Map
                if normal_enabled and normal_texture_node:
                    self._report_progress(context, 0.65, "Baking normal map...")
                    for node in nodes:
                        node.select = False
                    normal_texture_node.select = True
                    nodes.active = normal_texture_node
                    
                    # Explicitly pass selected-to-active settings into the operator
                    bpy.ops.object.bake(
                        type='NORMAL',
                        use_clear=True,
                        normal_space='TANGENT',
                        use_selected_to_active=True,
                        cage_extrusion=bake_cage_extrusion
                    )
                    
                    normal_image.filepath_raw = os.path.join(bakeFolder, f"{normal_image_name}.png")
                    normal_image.file_format = 'PNG'
                    normal_image.save()

                # Bake Diffuse Map
                if diffuse_enabled and diffuse_node:
                    self._report_progress(context, 0.85, "Baking diffuse map...")
                    bpy.context.scene.render.bake.use_pass_direct = False
                    bpy.context.scene.render.bake.use_pass_indirect = False
                    bpy.context.scene.render.bake.use_pass_color = True
                    
                    for node in nodes:
                        node.select = False
                    diffuse_node.select = True
                    nodes.active = diffuse_node
                    
                    # Explicitly pass selected-to-active settings into the operator
                    bpy.ops.object.bake(
                        type='DIFFUSE',
                        use_clear=True,
                        use_selected_to_active=True,
                        cage_extrusion=bake_cage_extrusion
                    )
                    
                    diffuse_image.filepath_raw = os.path.join(bakeFolder, f"{diffuse_image_name}.png")
                    diffuse_image.file_format = 'PNG'
                    diffuse_image.save()

                # Link up the texture nodes to the shader after baking is complete
                self._report_progress(context, 0.97, "Linking textures...")
                if normal_enabled and normal_texture_node and norm_map and bsdf_node:
                    links.new(normal_texture_node.outputs['Color'], norm_map.inputs['Color'])
                    links.new(norm_map.outputs['Normal'], bsdf_node.inputs['Normal'])

                if diffuse_enabled and diffuse_node and bsdf_node:
                    links.new(diffuse_node.outputs['Color'], bsdf_node.inputs['Base Color'])

            except Exception as e:
                self._report_progress(context, context.scene.retopo_progress, f"Failed: {e}")
                self.report({'ERROR'}, f"Error transferring detail to {original_obj_name}: {e}")
                return {'CANCELLED'}
        else:
            self.report({'ERROR'}, "Active object is not a valid mesh.")
            return {'CANCELLED'}

        self._report_progress(context, 1.0, "Completed")
        self.report({'INFO'}, "Remesh and texture transfer completed successfully")
        return {'FINISHED'}