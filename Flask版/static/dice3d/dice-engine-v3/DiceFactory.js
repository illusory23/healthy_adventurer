import * as CANNON from 'cannon-es';
import * as THREE from 'three';
import { DICE_GEOM } from './const/dice.js';
import { MATERIALTYPES } from './const/materialtypes.js';
import { DicePreset } from './DicePreset.js';
function getFaceValue() {
    const reason = this.resultReason;
    const vector = new THREE.Vector3(0, 0, this.shape === 'd4' ? -1 : 1);
    let closest_face;
    let closest_angle = Math.PI * 2;
    const normals = this.geometry.getAttribute('normal').array;
    for (let i = 0, l = this.geometry.groups.length; i < l; ++i) {
        const face = this.geometry.groups[i];
        if (face.materialIndex === 0)
            continue;
        const startVertex = i * 9;
        const normal = new THREE.Vector3(normals[startVertex], normals[startVertex + 1], normals[startVertex + 2]);
        const angle = normal
            .clone()
            .applyQuaternion(this.body.quaternion)
            .angleTo(vector);
        if (angle < closest_angle) {
            closest_angle = angle;
            closest_face = face;
        }
    }
    let matindex = (closest_face?.materialIndex ?? 1) - 1;
    let offset = 2;
    const diceobj = DiceFactory.dice[this.notation.type];
    if (this.shape === 'd4') {
        const labelindex2 = matindex - 1 === 0 ? 5 : matindex;
        const d4labels = diceobj.labels;
        return {
            value: matindex,
            label: d4labels[matindex - 1][labelindex2][0],
            reason,
        };
    }
    if (['d10', 'd2'].includes(this.shape)) {
        matindex += 1;
        offset -= 1;
    }
    const value = diceobj.values[(matindex - 1) % diceobj.values.length];
    const label = diceobj.labels[((matindex - 1) % (diceobj.labels.length - 2)) + offset];
    return { value, label, reason };
}
function storeRolledValue(reason) {
    this.resultReason = reason ?? this.resultReason;
    this.result.push(this.getFaceValue());
}
function getLastValue() {
    if (!this.result || this.result.length < 1) {
        return { value: undefined, label: '', reason: '' };
    }
    return this.result.at(-1);
}
function ignoreLastValue(ignore) {
    if (!this.result || this.result.length < 1)
        return;
    const lastvalue = this.getLastValue();
    lastvalue.ignore = ignore;
    this.setLastValue(lastvalue);
}
function setLastValue(result) {
    if (!this.result || this.result.length < 1)
        return;
    if (!result)
        return;
    this.result[this.result.length - 1] = result;
    return result;
}
class DiceFactory {
    constructor(options = {}) {
        this.baseScale = 100;
        this.bumpMapping = true;
        this.geometries = {};
        this.materials_cache = {};
        this.cache_hits = 0;
        this.cache_misses = 0;
        this.label_color = '';
        this.dice_color = '';
        this.edge_color = '';
        this.label_outline = '';
        this.dice_texture = '';
        this.dice_material = '';
        this.dice_color_rand = '';
        this.label_color_rand = '';
        this.label_outline_rand = '';
        this.dice_texture_rand = '';
        this.dice_material_rand = '';
        this.edge_color_rand = '';
        this.material_options = {
            specular: 0xffffff,
            color: 0xb5b5b5,
            shininess: 5,
            flatShading: true,
        };
        Object.assign(this, options);
    }
    updateConfig(options = {}) {
        Object.assign(this, options);
        if (options.scale) {
            this.scaleGeometry();
        }
    }
    setBumpMapping(bumpMapping) {
        this.bumpMapping = bumpMapping;
        this.materials_cache = {};
    }
    create(type) {
        const diceobj = this.get(type);
        if (!diceobj)
            return null;
        let geom = this.geometries[type];
        if (!geom) {
            const created = this.createGeometry(diceobj.shape, diceobj.scale * this.baseScale);
            if (!(created instanceof THREE.BufferGeometry))
                return null;
            geom = created;
            this.geometries[type] = geom;
        }
        this.setMaterialInfo();
        const materials = this.createMaterials(diceobj, this.baseScale / 2, 1);
        const dicemesh = new THREE.Mesh(geom, materials);
        dicemesh.result = [];
        dicemesh.shape = diceobj.shape;
        dicemesh.rerolls = 0;
        dicemesh.resultReason = 'natural';
        dicemesh.mass = diceobj.mass;
        dicemesh.flickable = false;
        dicemesh.flickOnSettled = false;
        dicemesh.getFaceValue = getFaceValue;
        dicemesh.storeRolledValue = storeRolledValue;
        dicemesh.getLastValue = getLastValue;
        dicemesh.ignoreLastValue = ignoreLastValue;
        dicemesh.setLastValue = setLastValue;
        if (diceobj.color) {
            const face = materials[0];
            face.color = new THREE.Color(diceobj.color);
            face.emissive = new THREE.Color(diceobj.color);
            face.emissiveIntensity = 1;
            face.needsUpdate = true;
        }
        const unique_sides = diceobj.values.length;
        if (unique_sides >= 1 && unique_sides <= 3) {
            return this.fixmaterials(dicemesh, unique_sides);
        }
        return dicemesh;
    }
    get(type) {
        if (Object.hasOwn(DiceFactory.dice, type)) {
            return DiceFactory.dice[type];
        }
        const dieSet = new DicePreset(type);
        DiceFactory.dice[type] = dieSet;
        return dieSet;
    }
    getGeometry(type) {
        return this.geometries[type];
    }
    scaleGeometry() { }
    createMaterials(diceobj, size, margin, allowcache = true, d4specialindex = 0) {
        let labels = diceobj.labels;
        if (diceobj.shape === 'd4') {
            labels = diceobj.labels[d4specialindex];
            size = this.baseScale / 2;
            margin = this.baseScale * 2;
        }
        const materials = [];
        for (let i = 0; i < labels.length; ++i) {
            materials.push(this.buildFaceMaterial(diceobj, labels, i, size, margin, allowcache));
        }
        return materials;
    }
    buildFaceMaterial(diceobj, labels, index, size, margin, allowcache) {
        const isEdge = index === 0;
        const mat = this.baseMaterial();
        const canvasTextures = this.createTextMaterial(diceobj, labels, index, size, margin, {
            texture: isEdge ? this.edgeTexture() : this.dice_texture_rand,
            fore: this.label_color_rand,
            outline: this.label_outline_rand,
            back: isEdge ? this.edge_color_rand : this.dice_color_rand,
        }, allowcache);
        mat.map = canvasTextures?.composite ?? null;
        if (!isEdge && this.bumpMapping) {
            mat.bumpScale = this.bumpScaleFor(size);
            if (canvasTextures?.bump) {
                mat.bumpMap = canvasTextures.bump;
            }
            if (diceobj.shape !== 'd4' && diceobj.normals[index]) {
                mat.bumpMap = new THREE.Texture(diceobj.normals[index]);
                mat.bumpScale = 4;
                mat.bumpMap.needsUpdate = true;
            }
        }
        mat.opacity = 1;
        mat.transparent = true;
        mat.depthTest = false;
        return mat;
    }
    baseMaterial() {
        if (this.dice_material !== 'none') {
            const mat = new THREE.MeshStandardMaterial(MATERIALTYPES[this.dice_material]);
            mat.envMapIntensity = 0;
            return mat;
        }
        return new THREE.MeshPhongMaterial(this.material_options);
    }
    edgeTexture() {
        const rand = this.dice_texture_rand;
        if (typeof rand !== 'string' && rand.composite !== 'source-over')
            return rand;
        return { name: 'none' };
    }
    bumpScaleFor(size) {
        if (size > 45)
            return 4;
        if (size > 40)
            return 2.5;
        if (size > 35)
            return 1;
        return 0.75;
    }
    createTextMaterial(diceobj, labels, index, size, margin, style, allowcache) {
        if (labels[index] === undefined)
            return null;
        const resolved = style.texture || this.dice_texture_rand;
        const tex = typeof resolved === 'string' ? { name: resolved || 'none' } : resolved;
        const colors = {
            fore: style.fore || this.label_color_rand,
            outline: style.outline || this.label_outline_rand,
            back: style.back || this.dice_color_rand,
        };
        const text = labels[index];
        const cachestring = this.faceCacheKey(diceobj, text, index, tex, colors);
        if (allowcache && this.materials_cache[cachestring] != null) {
            this.cache_hits++;
            return this.materials_cache[cachestring];
        }
        const canvas = document.createElement('canvas');
        const context = canvas.getContext('2d', { alpha: true });
        context.globalAlpha = 0;
        context.clearRect(0, 0, canvas.width, canvas.height);
        const canvasBump = document.createElement('canvas');
        const contextBump = canvasBump.getContext('2d', { alpha: true });
        contextBump.globalAlpha = 0;
        contextBump.clearRect(0, 0, canvasBump.width, canvasBump.height);
        let ts;
        if (diceobj.shape === 'd4') {
            ts = this.calc_texture_size(size + margin) * 4;
        }
        else {
            ts = this.calc_texture_size(size + size * 2 * margin) * 4;
        }
        canvas.width = canvas.height = ts;
        canvasBump.width = canvasBump.height = ts;
        context.fillStyle = colors.back;
        context.fillRect(0, 0, canvas.width, canvas.height);
        contextBump.fillStyle = '#FFFFFF';
        contextBump.fillRect(0, 0, canvasBump.width, canvasBump.height);
        if (tex.texture && tex.name !== '' && tex.name !== 'none') {
            context.globalCompositeOperation =
                tex.composite || 'source-over';
            context.drawImage(tex.texture, 0, 0, canvas.width, canvas.height);
            context.globalCompositeOperation = 'source-over';
            if (tex.bump) {
                contextBump.globalCompositeOperation = 'source-over';
                contextBump.drawImage(tex.bump, 0, 0, canvas.width, canvas.height);
            }
        }
        else {
            context.globalCompositeOperation = 'source-over';
        }
        context.globalCompositeOperation = 'source-over';
        context.textAlign = 'center';
        context.textBaseline = 'middle';
        contextBump.textAlign = 'center';
        contextBump.textBaseline = 'middle';
        const contexts = { ctx: context, bump: contextBump, canvas };
        let isTexture = false;
        if (diceobj.shape === 'd4') {
            this.drawD4Face(contexts, text, diceobj, ts, colors);
        }
        else {
            isTexture = this.drawPolyFace(contexts, text, diceobj, index, ts, margin, colors);
        }
        const compositetexture = new THREE.CanvasTexture(canvas);
        const bumpMap = isTexture ? null : new THREE.CanvasTexture(canvasBump);
        if (allowcache) {
            this.cache_misses++;
            this.materials_cache[cachestring] = {
                composite: compositetexture,
                bump: bumpMap,
            };
        }
        return { composite: compositetexture, bump: bumpMap };
    }
    // Build a stable cache-key fragment from a face label. d4 labels are nested
    // arrays that also contain numbers (e.g. `[0, 0, 0]`), so anything that isn't
    // a string/image/array is coerced rather than treated as an array.
    labelKey(label) {
        if (typeof label === 'string')
            return label;
        if (label instanceof HTMLImageElement)
            return label.src;
        if (Array.isArray(label))
            return label.map(part => this.labelKey(part)).join(',');
        return String(label);
    }
    faceCacheKey(diceobj, text, index, tex, colors) {
        const textCache = this.labelKey(text);
        const { fore, outline, back } = colors;
        if (diceobj.shape === 'd4') {
            return diceobj.type + textCache + tex.name + fore + outline + back;
        }
        return diceobj.type + textCache + index + tex.name + fore + outline + back;
    }
    faceRotationDegrees(shape, index) {
        const rotate = {
            d8: { even: -7.5, odd: -127.5 },
            d10: { all: -6 },
            d12: { all: 5 },
            d20: { all: -7.5 },
        };
        const rotateface = rotate[shape];
        if (!rotateface)
            return 0;
        if (Object.hasOwn(rotateface, 'all'))
            return rotateface.all ?? 0;
        if (index > 0 && index % 2 !== 0)
            return rotateface.odd ?? 0;
        return rotateface.even ?? 0;
    }
    drawPolyFace({ ctx, bump, canvas }, text, diceobj, index, ts, margin, colors) {
        const degrees = this.faceRotationDegrees(diceobj.shape, index);
        if (degrees) {
            const hw = canvas.width / 2;
            const hh = canvas.height / 2;
            ctx.translate(hw, hh);
            ctx.rotate(degrees * (Math.PI / 180));
            ctx.translate(-hw, -hh);
            bump.translate(hw, hh);
            bump.rotate(degrees * (Math.PI / 180));
            bump.translate(-hw, -hh);
        }
        if (text instanceof HTMLImageElement) {
            ctx.drawImage(text, 0, 0, text.width, text.height, 0, 0, canvas.width, canvas.height);
            return true;
        }
        const label = text;
        let fontsize = ts / (1 + 2 * margin);
        let textstarty = canvas.height / 2 + 10;
        let textstartx = canvas.width / 2;
        if (diceobj.shape === 'd10') {
            fontsize = fontsize * 0.75;
            textstarty = textstarty * 1.15 - 10;
        }
        else if (diceobj.shape === 'd20') {
            textstartx = textstartx * 0.98;
        }
        ctx.font = fontsize + 'pt ' + diceobj.font;
        bump.font = fontsize + 'pt ' + diceobj.font;
        let lineHeight = ctx.measureText('M').width * 1.4;
        const textlines = label.split('\n');
        if (textlines.length > 1) {
            fontsize = fontsize / textlines.length;
            ctx.font = fontsize + 'pt ' + diceobj.font;
            bump.font = fontsize + 'pt ' + diceobj.font;
            lineHeight = ctx.measureText('M').width * 1.2;
            textstarty -= (lineHeight * textlines.length) / 2;
        }
        for (const line of textlines) {
            this.drawTextLine(ctx, bump, line, textstartx, textstarty, colors);
            textstarty += lineHeight * 1.5;
        }
        return false;
    }
    drawTextLine(ctx, bump, line, x, y, colors) {
        const trimmed = line.trim();
        const { fore, outline, back } = colors;
        if (outline !== 'none' && outline !== back) {
            ctx.strokeStyle = outline;
            ctx.lineWidth = 5;
            ctx.strokeText(line, x, y);
            bump.strokeStyle = '#000000';
            bump.lineWidth = 5;
            bump.strokeText(line, x, y);
            if (trimmed === '6' || trimmed === '9') {
                ctx.strokeText('  .', x, y);
                bump.strokeText('  .', x, y);
            }
        }
        ctx.fillStyle = fore;
        ctx.fillText(line, x, y);
        bump.fillStyle = '#000000';
        bump.fillText(line, x, y);
        if (trimmed === '6' || trimmed === '9') {
            ctx.fillText('  .', x, y);
            bump.fillText('  .', x, y);
        }
    }
    drawD4Face({ ctx, bump, canvas }, glyphs, diceobj, ts, colors) {
        const hw = canvas.width / 2;
        const hh = canvas.height / 2;
        const { fore, outline, back } = colors;
        ctx.font = (ts / 128) * 24 + 'pt ' + diceobj.font;
        bump.font = (ts / 128) * 24 + 'pt ' + diceobj.font;
        for (const glyph of glyphs) {
            if (glyph instanceof HTMLImageElement) {
                const scaleTexture = glyph.width / canvas.width;
                ctx.drawImage(glyph, 0, 0, glyph.width, glyph.height, 100 / scaleTexture, 25 / scaleTexture, 60 / scaleTexture, 60 / scaleTexture);
            }
            else {
                const ch = glyph;
                if (outline !== 'none' && outline !== back) {
                    ctx.strokeStyle = outline;
                    ctx.lineWidth = 5;
                    ctx.strokeText(ch, hw, hh - ts * 0.3);
                    bump.strokeStyle = '#000000';
                    bump.lineWidth = 5;
                    bump.strokeText(ch, hw, hh - ts * 0.3);
                }
                ctx.fillStyle = fore;
                ctx.fillText(ch, hw, hh - ts * 0.3);
                bump.fillStyle = '#000000';
                bump.fillText(ch, hw, hh - ts * 0.3);
            }
            ctx.translate(hw, hh);
            ctx.rotate((Math.PI * 2) / 3);
            ctx.translate(-hw, -hh);
            bump.translate(hw, hh);
            bump.rotate((Math.PI * 2) / 3);
            bump.translate(-hw, -hh);
        }
    }
    applyColorSet(colordata, _prevtexture, _prevmaterial) {
        this.colordata = colordata;
        this.label_color = colordata.foreground;
        this.dice_color = colordata.background;
        this.label_outline = colordata.outline;
        this.dice_texture = colordata.texture;
        this.dice_material = colordata.texture.material ?? 'none';
        this.edge_color =
            (Object.hasOwn(colordata, 'edge') ? colordata.edge : colordata.background) ??
                colordata.background;
    }
    setMaterialInfo() {
        const prevcolordata = this.colordata;
        const prevtexture = this.dice_texture;
        const prevmaterial = this.dice_material;
        this.resetRandomChoices();
        this.resolveBaseColors();
        this.resolveEdgeColor();
        this.resolveLabelColor();
        this.resolveLabelOutline();
        this.resolveTexture();
        this.resolveMaterial();
        if (this.colordata && this.colordata.id !== prevcolordata?.id) {
            this.applyColorSet(this.colordata, prevtexture, prevmaterial);
        }
    }
    randomItem(list) {
        return list[Math.floor(Math.random() * list.length)];
    }
    resetRandomChoices() {
        this.dice_color_rand = '';
        this.label_color_rand = '';
        this.label_outline_rand = '';
        this.dice_texture_rand = '';
        this.dice_material_rand = '';
        this.edge_color_rand = '';
    }
    resolveBaseColors() {
        const diceColor = this.dice_color;
        if (!Array.isArray(diceColor)) {
            this.dice_color_rand = diceColor;
            return;
        }
        const colorindex = Math.floor(Math.random() * diceColor.length);
        if (Array.isArray(this.label_color) && this.label_color.length === diceColor.length) {
            this.label_color_rand = this.label_color[colorindex];
            if (Array.isArray(this.label_outline) &&
                this.label_outline.length === this.label_color.length) {
                this.label_outline_rand = this.label_outline[colorindex];
            }
        }
        if (Array.isArray(this.dice_texture) &&
            this.dice_texture.length === diceColor.length) {
            const tex = this.dice_texture[colorindex];
            this.dice_texture_rand = tex;
            this.dice_material_rand = tex.material ?? '';
        }
        if (Array.isArray(this.edge_color) && this.edge_color.length === diceColor.length) {
            this.edge_color_rand = this.edge_color[colorindex];
        }
        this.dice_color_rand = diceColor[colorindex];
    }
    resolveEdgeColor() {
        if (this.edge_color_rand !== '')
            return;
        this.edge_color_rand = Array.isArray(this.edge_color)
            ? this.randomItem(this.edge_color)
            : this.edge_color;
    }
    resolveLabelColor() {
        if (this.label_color_rand === '' && Array.isArray(this.label_color)) {
            const colorindex = this.randomItem(this.label_color);
            if (Array.isArray(this.label_outline) &&
                this.label_outline.length === this.label_color.length) {
                this.label_outline_rand = this.label_outline[colorindex];
            }
            this.label_color_rand = this.label_color[colorindex];
        }
        else if (this.label_color_rand === '') {
            this.label_color_rand = this.label_color;
        }
    }
    resolveLabelOutline() {
        if (this.label_outline_rand === '' && Array.isArray(this.label_outline)) {
            const colorindex = this.randomItem(this.label_outline);
            this.label_outline_rand = this.label_outline[colorindex];
        }
        else if (this.label_outline_rand === '') {
            this.label_outline_rand = this.label_outline;
        }
    }
    resolveTexture() {
        if (this.dice_texture_rand === '' && Array.isArray(this.dice_texture)) {
            const tex = this.randomItem(this.dice_texture);
            this.dice_texture_rand = tex;
            this.dice_material_rand = tex.material ?? this.dice_material;
        }
        else if (this.dice_texture_rand === '') {
            const tex = this.dice_texture;
            this.dice_texture_rand = tex;
            this.dice_material_rand =
                (typeof tex === 'string' ? '' : (tex.material ?? '')) || this.dice_material;
        }
    }
    resolveMaterial() {
        if (this.dice_material_rand === '' && Array.isArray(this.dice_material)) {
            this.dice_material_rand = this.randomItem(this.dice_material);
        }
        else if (this.dice_material_rand === '') {
            this.dice_material_rand = this.dice_material;
        }
    }
    calc_texture_size(approx) {
        return 2 ** Math.floor(Math.log2(approx));
    }
    createGeometry(type, radius, onlyShape = false) {
        const build = (vertices, faces, tab, af, chamfer) => onlyShape
            ? this.create_shape(vertices, faces, radius)
            : this.create_geom(vertices, faces, radius, tab, af, chamfer);
        switch (type) {
            case 'd2': {
                const geom = new THREE.CylinderGeometry(1 * radius, 1 * radius, 0.1 * radius, 32);
                geom.cannon_shape = new CANNON.Cylinder(1 * radius, 1 * radius, 0.1 * radius, 8);
                return geom;
            }
            case 'd4':
                return build(DICE_GEOM.d4.vertices, DICE_GEOM.d4.faces, -0.1, (Math.PI * 7) / 6, 0.96);
            case 'd6':
                return build(DICE_GEOM.d6.vertices, DICE_GEOM.d6.faces, 0.1, Math.PI / 4, 0.96);
            case 'd8':
                return build(DICE_GEOM.d8.vertices, DICE_GEOM.d8.faces, 0, -Math.PI / 4 / 2, 0.965);
            case 'd10':
                return build(DICE_GEOM.d10.vertices, DICE_GEOM.d10.faces, 0.3, Math.PI, 0.945);
            case 'd12':
                return build(DICE_GEOM.d12.vertices, DICE_GEOM.d12.faces, 0.2, -Math.PI / 4 / 2, 0.968);
            case 'd20':
                return build(DICE_GEOM.d20.vertices, DICE_GEOM.d20.faces, -0.2, -Math.PI / 4 / 2, 0.955);
            default:
                console.error(`Geometry for ${type} is not available`);
                return null;
        }
    }
    fixmaterials(mesh, unique_sides) {
        for (let i = 0, l = mesh.geometry.groups.length; i < l; ++i) {
            const matindex = (mesh.geometry.groups[i].materialIndex ?? 0) - 2;
            if (matindex < unique_sides)
                continue;
            const modmatindex = matindex % unique_sides;
            mesh.geometry.groups[i].materialIndex = modmatindex + 2;
        }
        return mesh;
    }
    create_shape(vertices, faces, radius) {
        const vectors = new Array(vertices.length);
        for (let i = 0; i < vertices.length; ++i) {
            vectors[i] = new THREE.Vector3().fromArray(vertices[i]).normalize();
        }
        const cv = new Array(vertices.length);
        const cf = new Array(faces.length);
        for (let i = 0; i < vectors.length; ++i) {
            const v = vectors[i];
            cv[i] = new CANNON.Vec3(v.x * radius, v.y * radius, v.z * radius);
        }
        for (let i = 0; i < faces.length; ++i) {
            cf[i] = faces[i].slice(0, -1);
        }
        return new CANNON.ConvexPolyhedron({ vertices: cv, faces: cf });
    }
    make_geom(vertices, faces, radius, tab, af) {
        const geom = new THREE.BufferGeometry();
        for (let i = 0; i < vertices.length; ++i) {
            vertices[i] = vertices[i].multiplyScalar(radius);
        }
        const positions = [];
        const normals = [];
        const uvs = [];
        const cb = new THREE.Vector3();
        const ab = new THREE.Vector3();
        let materialIndex = 0;
        let faceFirstVertexIndex = 0;
        for (const ii of faces) {
            const fl = ii.length - 1;
            const aa = (Math.PI * 2) / fl;
            materialIndex = ii[fl] + 1;
            for (let j = 0; j < fl - 2; ++j) {
                positions.push(...vertices[ii[0]].toArray(), ...vertices[ii[j + 1]].toArray(), ...vertices[ii[j + 2]].toArray());
                cb.subVectors(vertices[ii[j + 2]], vertices[ii[j + 1]]);
                ab.subVectors(vertices[ii[0]], vertices[ii[j + 1]]);
                cb.cross(ab);
                cb.normalize();
                const normal = cb.toArray();
                normals.push(...normal, ...normal, ...normal);
                // UVs
                uvs.push((Math.cos(af) + 1 + tab) / 2 / (1 + tab), (Math.sin(af) + 1 + tab) / 2 / (1 + tab), (Math.cos(aa * (j + 1) + af) + 1 + tab) / 2 / (1 + tab), (Math.sin(aa * (j + 1) + af) + 1 + tab) / 2 / (1 + tab), (Math.cos(aa * (j + 2) + af) + 1 + tab) / 2 / (1 + tab), (Math.sin(aa * (j + 2) + af) + 1 + tab) / 2 / (1 + tab));
            }
            const numOfVertices = (fl - 2) * 3;
            for (let k = 0; k < numOfVertices / 3; k++) {
                geom.addGroup(faceFirstVertexIndex, 3, materialIndex);
                faceFirstVertexIndex += 3;
            }
        }
        geom.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3));
        geom.setAttribute('normal', new THREE.Float32BufferAttribute(normals, 3));
        geom.setAttribute('uv', new THREE.Float32BufferAttribute(uvs, 2));
        geom.boundingSphere = new THREE.Sphere(new THREE.Vector3(), radius);
        return geom;
    }
    make_d10_geom(vertices, faces, radius, tab, af) {
        const geom = new THREE.BufferGeometry();
        for (let i = 0; i < vertices.length; ++i) {
            vertices[i] = vertices[i].multiplyScalar(radius);
        }
        const positions = [];
        const normals = [];
        const uvs = [];
        const cb = new THREE.Vector3();
        const ab = new THREE.Vector3();
        let materialIndex = 0;
        let faceFirstVertexIndex = 0;
        for (const ii of faces) {
            const fl = ii.length - 1;
            const aa = (Math.PI * 2) / fl;
            materialIndex = ii[fl] + 1;
            const w = 0.65;
            const h = 0.85;
            const v0 = 1 - 1 * h;
            const v1 = 1 - (0.895 / 1.105) * h;
            const v2 = 1;
            for (let j = 0; j < fl - 2; ++j) {
                positions.push(...vertices[ii[0]].toArray(), ...vertices[ii[j + 1]].toArray(), ...vertices[ii[j + 2]].toArray());
                cb.subVectors(vertices[ii[j + 2]], vertices[ii[j + 1]]);
                ab.subVectors(vertices[ii[0]], vertices[ii[j + 1]]);
                cb.cross(ab);
                cb.normalize();
                const normal = cb.toArray();
                normals.push(...normal, ...normal, ...normal);
                if (ii.at(-1) === -1 || j >= 2) {
                    uvs.push((Math.cos(af) + 1 + tab) / 2 / (1 + tab), (Math.sin(af) + 1 + tab) / 2 / (1 + tab), (Math.cos(aa * (j + 1) + af) + 1 + tab) / 2 / (1 + tab), (Math.sin(aa * (j + 1) + af) + 1 + tab) / 2 / (1 + tab), (Math.cos(aa * (j + 2) + af) + 1 + tab) / 2 / (1 + tab), (Math.sin(aa * (j + 2) + af) + 1 + tab) / 2 / (1 + tab));
                }
                else if (j === 0) {
                    uvs.push(0.5 - w / 2, v1, 0.5, v0, 0.5 + w / 2, v1);
                }
                else if (j === 1) {
                    uvs.push(0.5 - w / 2, v1, 0.5 + w / 2, v1, 0.5, v2);
                }
            }
            const numOfVertices = (fl - 2) * 3;
            for (let k = 0; k < numOfVertices / 3; k++) {
                geom.addGroup(faceFirstVertexIndex, 3, materialIndex);
                faceFirstVertexIndex += 3;
            }
        }
        geom.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3));
        geom.setAttribute('normal', new THREE.Float32BufferAttribute(normals, 3));
        geom.setAttribute('uv', new THREE.Float32BufferAttribute(uvs, 2));
        geom.boundingSphere = new THREE.Sphere(new THREE.Vector3(), radius);
        return geom;
    }
    chamfer_geom(vectors, faces, chamfer) {
        const { chamfer_vectors, chamfer_faces, corner_faces } = this.chamferBevelFaces(vectors, faces, chamfer);
        this.chamferEdgeFaces(faces, chamfer_faces);
        this.chamferCornerFaces(faces, chamfer_faces, corner_faces);
        return { vectors: chamfer_vectors, faces: chamfer_faces };
    }
    chamferBevelFaces(vectors, faces, chamfer) {
        const chamfer_vectors = [];
        const chamfer_faces = [];
        const corner_faces = new Array(vectors.length);
        for (let i = 0; i < vectors.length; ++i)
            corner_faces[i] = [];
        for (const ii of faces) {
            const fl = ii.length - 1;
            const center_point = new THREE.Vector3();
            const face = new Array(fl);
            for (let j = 0; j < fl; ++j) {
                const vv = vectors[ii[j]].clone();
                center_point.add(vv);
                face[j] = chamfer_vectors.push(vv) - 1;
                corner_faces[ii[j]].push(face[j]);
            }
            center_point.divideScalar(fl);
            for (let j = 0; j < fl; ++j) {
                const vv = chamfer_vectors[face[j]];
                vv.subVectors(vv, center_point)
                    .multiplyScalar(chamfer)
                    .addVectors(vv, center_point);
            }
            face.push(ii[fl]);
            chamfer_faces.push(face);
        }
        return { chamfer_vectors, chamfer_faces, corner_faces };
    }
    chamferEdgeFaces(faces, chamfer_faces) {
        for (let i = 0; i < faces.length - 1; ++i) {
            for (let j = i + 1; j < faces.length; ++j) {
                const pairs = this.sharedEdgePairs(faces, i, j);
                if (pairs.length !== 4)
                    continue;
                chamfer_faces.push([
                    chamfer_faces[pairs[0][0]][pairs[0][1]],
                    chamfer_faces[pairs[1][0]][pairs[1][1]],
                    chamfer_faces[pairs[3][0]][pairs[3][1]],
                    chamfer_faces[pairs[2][0]][pairs[2][1]],
                    -1,
                ]);
            }
        }
    }
    sharedEdgePairs(faces, i, j) {
        const pairs = [];
        let lastm = -1;
        for (let m = 0; m < faces[i].length - 1; ++m) {
            const n = faces[j].indexOf(faces[i][m]);
            if (n < 0 || n >= faces[j].length - 1)
                continue;
            if (lastm >= 0 && m !== lastm + 1)
                pairs.unshift([i, m], [j, n]);
            else
                pairs.push([i, m], [j, n]);
            lastm = m;
        }
        return pairs;
    }
    chamferCornerFaces(faces, chamfer_faces, corner_faces) {
        for (const cf of corner_faces) {
            const face = [cf[0]];
            let count = cf.length - 1;
            while (count) {
                const next = this.nextCornerVertex(faces, chamfer_faces, cf, face);
                if (next !== undefined)
                    face.push(next);
                --count;
            }
            face.push(-1);
            chamfer_faces.push(face);
        }
    }
    nextCornerVertex(faces, chamfer_faces, cf, face) {
        for (let m = faces.length; m < chamfer_faces.length; ++m) {
            let index = chamfer_faces[m].indexOf(face.at(-1));
            if (index < 0 || index >= 4)
                continue;
            if (--index === -1)
                index = 3;
            const next_vertex = chamfer_faces[m][index];
            if (cf.includes(next_vertex))
                return next_vertex;
        }
        return undefined;
    }
    create_geom(vertices, faces, radius, tab, af, chamfer) {
        const vectors = new Array(vertices.length);
        for (let i = 0; i < vertices.length; ++i) {
            vectors[i] = new THREE.Vector3().fromArray(vertices[i]).normalize();
        }
        const cg = this.chamfer_geom(vectors, faces, chamfer);
        const geom = faces.length === 10
            ? this.make_d10_geom(cg.vectors, cg.faces, radius, tab, af)
            : this.make_geom(cg.vectors, cg.faces, radius, tab, af);
        geom.cannon_shape = this.create_shape(vertices, faces, radius);
        geom.name = 'd' + faces.length;
        return geom;
    }
}
DiceFactory.dice = {};
export { DiceFactory };
