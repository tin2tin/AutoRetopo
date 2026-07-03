# AutoRetopo
A powerful retopology and re-texturing tool designed for high-poly meshes (photogrammetry, AI-generated 3D models, scans, etc.). AutoRetopo automatically generates a clean, quad-based mesh with significantly lower polygon count while preserving surface detail through intelligent normal map baking.

![screenshot](https://github.com/ClaireOzzz/ImageURLhost/blob/main/BlenderAddon.png)

## Features

### Remeshing
- **Voxel Remeshing**: Converts high-poly geometry into a clean mesh using adaptive voxelization with adjustable detail level
- **Quad Face Remeshing**: Generates quad-based topology with user-controlled face count (1-50,000 faces)
- **Pre-Smoothing**: Removes small-scale noise and debris before remeshing (useful for messy scans with hair, self-intersections, etc.)
- **Smart Island Merging**: Automatically welds disconnected debris islands back to the main surface instead of discarding them
- **Tiny Shell Removal**: Eliminates floating artifacts from the voxel remeshing process

### Texture Baking
- **Diffuse Texture**: Bakes color information from the original high-poly mesh
- **Normal Map**: Generates high-quality normal maps to preserve surface detail on the low-poly mesh
- **Configurable Texture Size**: From 1px to 50,000px resolution (default 2048px)

### Output
- **Custom Output Path**: Save results to any directory
- **Progress Tracking**: Real-time progress reporting during remesh operations

## Installation

1. Download this repository as a ZIP file
2. Open Blender and go to **Edit → Preferences**
3. Navigate to **Add-ons** and click **Install**
4. Select the downloaded ZIP file (AutoRetopo)
5. Enable the add-on by checking the checkbox
6. The AutoRetopo panel will appear in the 3D viewport sidebar (press `N` if not visible)

## Usage

1. Select a high-poly mesh in your scene
2. In the AutoRetopo panel, adjust the remeshing parameters:
   - **Voxel Detail**: Lower values preserve finer detail; higher values create coarser meshes
   - **Pre-Smooth**: Increase for noisier scans (typically 50-150 for dense photogrammetry)
   - **Quad Faces**: Toggle quad remeshing and set target face count
3. Configure texture baking options (Diffuse, Normal, texture size)
4. Set the output folder
5. Click **Apply Remesh** and wait for completion

## To be added in the future

- Ambient Occlusion (AO) map
- Roughness map
- Metallic map support
- Enhanced mesh optimization controls
