# Models, animations and particles

NSBMD models in `<nds/model>`, their animations in `<nds/anim>`, the glTF writer in
`<nds/gltf>` and SPL particle archives in `<nds/spl>`. Every function and type is also in
the [API reference](api.md).

```eskiu
NdsModel m = nsbmd_open(bmd.data, bmd.len, 0)?;   // model 0 of nsbmd_count(...)
NdsMesh mesh = m.mesh()?;                         // posed, skinned, in model space
NdsAnimFile a = nds_anim_read(bca.data, bca.len)?;  // BCA0, BTA0, BTP0 or BMA0
NdsGltfOptions opt = nds_gltf_options();
nds_gltf_write(&m, &ts, &a, 1, "out", "model", &opt)?;
NdsSpl s = spl_read(spa.data, spa.len)?;
s.write_json("out", "fx")?;                       // the Tallgrass particle format
```

## Models

`nsbmd_open` reads a model's nodes (translation, a 3x3 rotation that may be a packed
"pivot" matrix, and scale), its inverse bind matrices, its materials with their drawing
state (diffuse, ambient, specular and emission colors, polygon alpha, culling, the
texture's repeat and mirror flags and the texture matrix) and keeps copies of its render
commands and pieces. `groups` still holds the triangles by material with no node matrix
applied, as `nsbmd_read` always gave them.

`NdsModel_mesh` runs the render commands as the DS does: node matrices multiplied onto
the current matrix, the 32-slot matrix stack, the skinning command that blends stack
matrices with inverse bind matrices, the model's scale up and down, and the GPU
commands of each piece (matrix restore and scale included). Every vertex comes out in
model space at rest.

It also records, for each vertex, the symbolic matrix it was drawn with: a weighted sum
of chains of node matrices. Each distinct chain becomes a joint (`NdsJoint`), so the
joint tree is the tree of chains the commands build, and each vertex gets the joints of
its sum with their weights (the four largest, renormalized; `over4` counts vertices that
had more). A scale or an inverse bind matrix between two nodes is a constant joint; two
constants in a row are merged, and a scale up followed by its scale down disappears.

A node scaled to zero at rest (a part hidden until an animation grows it) would put all
its vertices on one point. The mesh binds such a node at scale 1 instead: the vertices
keep their shape, and the node's real rest transform, applied by the skin, still hides
them until an animation scales it up.

## Animations

`nds_anim_read` reads the four animation kinds into curves (`NdsCurve`): none, one
constant value, or samples every 1, 2 or 4 frames. `NdsCurve_at` reads any frame by
linear interpolation and holds the last sample. A curve of `n` frames sampled every
frame has `n` samples; sampled every 2 or 4 frames it has `(n >> 1) + 1` or
`(n >> 2) + 1`, the last one at frame `n` rounded down to the step.

| File | Contents | Units |
|---|---|---|
| BCA0 | per node: translation, rotation (3x3, from the pivot or the packed basis table), scale | model units |
| BTA0 | per material: texture scale, rotation (sine and cosine), translation | 1 is the whole texture |
| BTP0 | per material: from which frame each texture and palette is used | frames |
| BMA0 | per material: diffuse, ambient, specular, emission colors and alpha | 0 to 1 |

## glTF

`nds_gltf_write` writes `NAME.gltf`, `NAME.bin` and one PNG per texture and palette
pair. The mesh carries `JOINTS_0` and `WEIGHTS_0` and a skin over the joints; its node is
the parent of the top joints. Joint animations become ordinary translation, rotation and
scale channels with a key every frame. Materials use `KHR_materials_unlit`, nearest
filtering and the texture's wrap modes; A3I5 and A5I3 textures and partial alpha give
`BLEND`, a transparent color 0 or alpha 0 gives `MASK`.

glTF has no standard texture animation, so the material animations go to JSON files next
to the model, in the formats the Tallgrass engine reads:

- `NAME.uvanims.json`, the first SRT animation's translation per frame:
  `{"material": {"times": [s], "offsets": [[u, v]]}}`.
- `NAME.patterns.json`, the first pattern animation:
  `{"frames": n, "materials": {"material": [[frame, "image.png", "palette"]]}}`; every
  image a key names is written.
- `NAME.matanims.json`, the first color animation per frame:
  `{"frames": n, "materials": {"material": {"diffuse": [[r, g, b]], "ambient": ...,
  "specular": ..., "emission": ..., "alpha": [a]}}}`; a constant channel is one value.

With `pointer_anims` (the default) SRT animations are also written as
`KHR_animation_pointer` channels on the material's `KHR_texture_transform` offset, scale
and rotation, and color animations on `baseColorFactor` and `emissiveFactor`. Readers
that do not know the extension can drop those channels; the side files carry the same
values.

Differences from apicula's glTF, which these files replace: texture offsets are in
texture units (apicula divides the stored value by 32 and by the texture size in texels,
so its offsets are 128 / size times larger: 16 times for an 8-texel texture); curves
sampled every 2 or 4 frames keep their last sample; animations longer than 4095 frames
keep their length; weights are floats, not 8 bits; nodes scaled to zero at rest are bound
at scale 1 (above).

## Particles

`spl_read` reads an SPL archive (" APS", version "12_1", the only one in the three games
checked): each resource's emitter record, its optional scale, color, alpha and texture
animations, child particles and fields (gravity, random, magnet, spin, collision,
convergence), and the textures with their palettes. Values stay as stored (see the
module comment). Nothing is simulated.

`NdsSpl_json` writes the open particle format of the Tallgrass engine
(`"format": "tallgrass-spl-1"`): keys sorted, a zero or false value left out, as the
engine's converter writes it. `NdsSpl_write_json` adds each texture as `NAME_<i>.png`,
with 5-bit channels widened by repeating their bits, as the engine does.

## Limits

- The texture matrix of a material (scale in 74 materials of the three games, rotation
  in 46, translation in 257) is applied to texture coordinates as scale, rotation and
  translation in texture units. apicula applies only the scale, so the rotation's sign
  and the translation's unit have no reference to compare with.
- BTA rotation and scale animations are read and written, but no game file checked had
  an animated texture scale, and the rotation's direction is unverified.
- The DS lights vertices with normals; the glTF materials are unlit and a vertex color
  is reset to white where a normal is given, as apicula does.
- SPL fields and flags that no file of the three games sets keep the bit widths seen;
  an emitter shape above 8 is named `hemisphereVolume` without a file to confirm it.
