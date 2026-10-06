import * as CANNON from 'cannon-es';
import * as THREE from 'three';
import { THEMES } from './const/themes.js';
import { DiceColors } from './DiceColors.js';
import { DiceFactory } from './DiceFactory.js';
import { DiceNotation } from './DiceNotation.js';
// iOS/WebKit defers media buffering until a user gesture, so an un-gestured
// <audio> can fire neither `canplaythrough` nor `error`. Cap the wait so a
// deferred clip resolves (skipped) instead of hanging the load chain.
const AUDIO_LOAD_TIMEOUT_MS = 8000;
// Drag-to-flick tuning. Velocities are world units/sec, in the same scale as a
// normal throw's boost. Below the move threshold a release counts as a tap.
const DRAG_MOVE_THRESHOLD = 25;
const DRAG_GAIN = 1;
const DRAG_MAX_SPEED = 6000;
const DRAG_LAUNCH_Z = 250;
const RESET_DWELL_MS = 1200;
// Right-click-added dice are carried this far above the table so releasing the
// grab lets them drop, rather than sitting flat with the held die.
const CARRY_LIFT = 220;
function describeWebGLSupport() {
    const info = {
        userAgent: typeof navigator === 'undefined' ? 'n/a' : navigator.userAgent,
    };
    try {
        const canvas = document.createElement('canvas');
        const gl2 = canvas.getContext('webgl2');
        const gl1 = canvas.getContext('webgl');
        const gl = gl2 ?? gl1;
        info.webgl2 = !!gl2;
        info.webgl1 = !!gl1;
        if (gl) {
            const dbg = gl.getExtension('WEBGL_debug_renderer_info');
            info.renderer = dbg
                ? gl.getParameter(dbg.UNMASKED_RENDERER_WEBGL)
                : gl.getParameter(gl.RENDERER);
            info.vendor = dbg
                ? gl.getParameter(dbg.UNMASKED_VENDOR_WEBGL)
                : gl.getParameter(gl.VENDOR);
            info.maxTextureSize = gl.getParameter(gl.MAX_TEXTURE_SIZE);
        }
    }
    catch (probeError) {
        info.probeError = String(probeError);
    }
    return info;
}
const defaultConfig = {
    assetPath: './',
    framerate: 1 / 60,
    sounds: false,
    volume: 100,
    color_spotlight: 0xefdfd5,
    shadows: true,
    theme_surface: 'green-felt',
    sound_dieMaterial: 'plastic',
    theme_customColorset: null,
    theme_colorset: 'white',
    theme_texture: '',
    theme_material: 'glass',
    gravity_multiplier: 400,
    light_intensity: 0.7,
    baseScale: 100,
    strength: 1,
    iterationLimit: 1000,
    onRollComplete: () => { },
    onRerollComplete: () => { },
    onAddDiceComplete: () => { },
    onRemoveDiceComplete: () => { },
    onEmpty: () => { },
    enableDiceSelection: false,
    onDiceHover: () => { },
    onDiceClick: () => { },
    enableDiceDrag: false,
    dragRemoval: { style: 'reset', dwellMs: RESET_DWELL_MS },
    onDiceGrabbed: () => { },
    onSettled: () => { },
    enableDiceAdd: false,
    onDiceAdded: () => { },
};
class DiceBox {
    constructor(element_container, options = {}) {
        this.surface = '';
        // --- engine state ---
        this.initialized = false;
        this.soundsRequested = false;
        this.adaptive_timestep = false;
        this.last_time = 0;
        this.running = false;
        this.rolling = false;
        this.hoveredDice = null;
        this.dragging = null;
        this.draggingPartner = null;
        this.dragPartnerOffset = { x: 0, y: 0 };
        this.carriedUnits = [];
        this.carriedOffset = new Map();
        this.dragRestZ = 0;
        this.dragSamples = [];
        this.tableAtRest = false;
        this.disposed = false;
        this.iteration = 0;
        this.steps = 0;
        this.dieIndex = 0;
        this.throwGroupCounter = 0;
        this.currentThrowGroup = 1 << 2;
        this.soundDelay = 10;
        this.animstate = '';
        this.lastSoundType = '';
        this.lastSoundStep = 0;
        this.lastSound = 0;
        this.throwGroups = [];
        const container = document.querySelector(element_container);
        if (!container) {
            throw new Error(`[dice-engine] container not found for selector: ${element_container}`);
        }
        this.container = container;
        this.dimensions = new THREE.Vector2(this.container.clientWidth, this.container.clientHeight);
        this.display = {
            currentWidth: 0,
            currentHeight: 0,
            containerWidth: 0,
            containerHeight: 0,
            aspect: 0,
            scale: 0,
        };
        this.cameraHeight = { max: 0, close: 0, medium: 0, far: 0 };
        this.scene = new THREE.Scene();
        this.world = new CANNON.World();
        this.dice_body_material = new CANNON.Material();
        this.sounds_table = {};
        this.sounds_dice = {};
        this.box_body = {};
        this.diceList = [];
        this.notationVectors = null;
        this.selector = { animate: true, rotate: true, intersected: null, dice: [] };
        Object.assign(this, defaultConfig, options);
        this.DiceColors = new DiceColors({ assetPath: this.assetPath });
        this.DiceFactory = new DiceFactory({ baseScale: this.baseScale });
        this.DiceFactory.setBumpMapping(true);
        this.surface = THEMES[this.theme_surface].surface;
    }
    enableShadows() {
        this.shadows = true;
        if (this.renderer)
            this.renderer.shadowMap.enabled = this.shadows;
        if (this.light)
            this.light.castShadow = this.shadows;
        if (this.desk)
            this.desk.receiveShadow = this.shadows;
    }
    disableShadows() {
        this.shadows = false;
        if (this.renderer)
            this.renderer.shadowMap.enabled = this.shadows;
        if (this.light)
            this.light.castShadow = this.shadows;
        if (this.desk)
            this.desk.receiveShadow = this.shadows;
    }
    async initialize() {
        try {
            this.renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
        }
        catch (error) {
            console.error('[dice-engine] Failed to create WebGL renderer.', describeWebGLSupport(), error);
            throw error;
        }
        this.container.appendChild(this.renderer.domElement);
        this.renderer.shadowMap.enabled = this.shadows;
        this.renderer.shadowMap.type = THREE.PCFShadowMap;
        this.renderer.setClearColor(0x000000, 0);
        this.setDimensions(this.dimensions);
        this.world.gravity.set(0, 0, -9.8 * this.gravity_multiplier);
        this.world.broadphase = new CANNON.NaiveBroadphase();
        this.world.solver.iterations = 14;
        this.world.allowSleep = true;
        this.makeWorldBox();
        this.resizeWorld();
        await this.loadTheme({
            colorset: this.theme_colorset,
            texture: this.theme_texture,
            material: this.theme_material,
        }).catch(error => {
            console.error('[dice-engine] Unable to load theme/textures:', error);
            throw error instanceof Error ? error : new Error('Unable to load theme');
        });
        this.initialized = true;
        this.renderer.render(this.scene, this.camera);
        if (this.enableDiceSelection || this.enableDiceDrag)
            this.enableSelection();
    }
    enableSelection() {
        if (this.raycaster)
            return;
        this.raycaster = new THREE.Raycaster();
        this.mouse = new THREE.Vector2();
        if (this.enableDiceSelection) {
            this.onMouseMoveBound = (event) => this.onMouseMove(event);
            globalThis.addEventListener('mousemove', this.onMouseMoveBound);
        }
        if (this.enableDiceDrag) {
            this.dragNdc = new THREE.Vector2();
            this.tablePlane = new THREE.Plane(new THREE.Vector3(0, 0, 1), 0);
            this.onPointerDownBound = (event) => this.onPointerDown(event);
            this.onPointerMoveBound = (event) => this.onPointerMove(event);
            this.onPointerUpBound = (event) => this.onPointerUp(event);
            globalThis.addEventListener('pointerdown', this.onPointerDownBound, true);
            globalThis.addEventListener('pointermove', this.onPointerMoveBound, true);
            globalThis.addEventListener('pointerup', this.onPointerUpBound, true);
            if (this.enableDiceAdd) {
                this.onContextMenuBound = (event) => this.onContextMenu(event);
                globalThis.addEventListener('contextmenu', this.onContextMenuBound, true);
            }
        }
        else if (this.enableDiceSelection) {
            this.onMouseClickBound = (event) => this.onMouseClick(event);
            globalThis.addEventListener('click', this.onMouseClickBound, true);
        }
    }
    teardownSelection() {
        if (this.onMouseMoveBound)
            globalThis.removeEventListener('mousemove', this.onMouseMoveBound);
        if (this.onMouseClickBound)
            globalThis.removeEventListener('click', this.onMouseClickBound, true);
        if (this.onPointerDownBound)
            globalThis.removeEventListener('pointerdown', this.onPointerDownBound, true);
        if (this.onPointerMoveBound)
            globalThis.removeEventListener('pointermove', this.onPointerMoveBound, true);
        if (this.onPointerUpBound)
            globalThis.removeEventListener('pointerup', this.onPointerUpBound, true);
        if (this.onContextMenuBound)
            globalThis.removeEventListener('contextmenu', this.onContextMenuBound, true);
        this.onMouseMoveBound = undefined;
        this.onMouseClickBound = undefined;
        this.onPointerDownBound = undefined;
        this.onPointerMoveBound = undefined;
        this.onPointerUpBound = undefined;
        this.onContextMenuBound = undefined;
        this.hoveredDice = null;
        this.dragging = null;
        this.draggingPartner = null;
        this.carriedUnits = [];
        this.carriedOffset.clear();
    }
    ensureSoundsLoaded() {
        if (!this.sounds || this.soundsRequested)
            return;
        this.soundsRequested = true;
        this.loadSounds().catch(error => {
            console.error('[dice-engine] Failed to load sounds (non-fatal):', error);
        });
    }
    makeWorldBox() {
        if (Object.keys(this.box_body).length) {
            this.world.removeBody(this.box_body.desk);
            this.world.removeBody(this.box_body.topWall);
            this.world.removeBody(this.box_body.bottomWall);
            this.world.removeBody(this.box_body.leftWall);
            this.world.removeBody(this.box_body.rightWall);
            if (this.box_body.barrier)
                this.world.removeBody(this.box_body.barrier);
        }
        const desk_body_material = new CANNON.Material();
        const barrier_body_material = new CANNON.Material();
        this.world.addContactMaterial(new CANNON.ContactMaterial(desk_body_material, this.dice_body_material, {
            friction: 0.6,
            restitution: 0.5,
        }));
        this.world.addContactMaterial(new CANNON.ContactMaterial(barrier_body_material, this.dice_body_material, {
            friction: 0.6,
            restitution: 1,
        }));
        this.world.addContactMaterial(new CANNON.ContactMaterial(this.dice_body_material, this.dice_body_material, {
            friction: 0.6,
            restitution: 0.5,
        }));
        const { containerWidth, containerHeight } = this.display;
        this.box_body.desk = new CANNON.Body({
            allowSleep: false,
            mass: 0,
            shape: new CANNON.Plane(),
            material: desk_body_material,
        });
        this.world.addBody(this.box_body.desk);
        this.box_body.topWall = new CANNON.Body({
            allowSleep: false,
            mass: 0,
            shape: new CANNON.Plane(),
            material: barrier_body_material,
        });
        this.box_body.topWall.quaternion.setFromAxisAngle(new CANNON.Vec3(1, 0, 0), Math.PI / 2);
        this.box_body.topWall.position.set(0, containerHeight * 0.93, 0);
        this.world.addBody(this.box_body.topWall);
        this.box_body.bottomWall = new CANNON.Body({
            allowSleep: false,
            mass: 0,
            shape: new CANNON.Plane(),
            material: barrier_body_material,
        });
        this.box_body.bottomWall.quaternion.setFromAxisAngle(new CANNON.Vec3(1, 0, 0), -Math.PI / 2);
        this.box_body.bottomWall.position.set(0, -containerHeight * 0.93, 0);
        this.world.addBody(this.box_body.bottomWall);
        this.box_body.leftWall = new CANNON.Body({
            allowSleep: false,
            mass: 0,
            shape: new CANNON.Plane(),
            material: barrier_body_material,
        });
        this.box_body.leftWall.quaternion.setFromAxisAngle(new CANNON.Vec3(0, 1, 0), -Math.PI / 2);
        this.box_body.leftWall.position.set(containerWidth * 0.93, 0, 0);
        this.world.addBody(this.box_body.leftWall);
        this.box_body.rightWall = new CANNON.Body({
            allowSleep: false,
            mass: 0,
            shape: new CANNON.Plane(),
            material: barrier_body_material,
        });
        this.box_body.rightWall.quaternion.setFromAxisAngle(new CANNON.Vec3(0, 1, 0), Math.PI / 2);
        this.box_body.rightWall.position.set(-containerWidth * 0.93, 0, 0);
        this.world.addBody(this.box_body.rightWall);
        // Optional interior barrier: a solid slab across the width at a normalized y,
        // sitting from the desk up. Blocks rolling/flicked (DYNAMIC) dice from
        // crossing; grabbed (KINEMATIC) dice pass through, so dice can be dragged over
        // it but not roll back.
        if (this.barrier !== undefined) {
            const slabHalfZ = 140;
            const barrier = new CANNON.Body({
                allowSleep: false,
                mass: 0,
                shape: new CANNON.Box(new CANNON.Vec3(containerWidth, 6, slabHalfZ)),
                material: barrier_body_material,
            });
            barrier.position.set(0, this.barrier * containerHeight * 0.9, slabHalfZ);
            this.world.addBody(barrier);
            this.box_body.barrier = barrier;
        }
    }
    async loadTheme(themeConfig) {
        const colorData = this.theme_customColorset
            ? await this.DiceColors.makeColorSet(this.theme_customColorset)
            : await this.DiceColors.getColorSet(themeConfig);
        this.DiceFactory.applyColorSet(colorData);
        this.colorData = colorData;
    }
    async applyThemeForThrow(theme) {
        if (!theme)
            return;
        const colorData = theme.theme_customColorset
            ? await this.DiceColors.makeColorSet(theme.theme_customColorset)
            : await this.DiceColors.getColorSet({
                colorset: theme.theme_colorset ?? this.theme_colorset,
                texture: theme.theme_texture ?? this.theme_texture,
                material: theme.theme_material ?? this.theme_material,
            });
        this.DiceFactory.applyColorSet(colorData);
        this.colorData = colorData;
    }
    async loadSounds() {
        const surfaces = {
            felt: 7,
            wood_table: 7,
            wood_tray: 7,
            metal: 9,
        };
        const dieMaterials = {
            coin: 6,
            metal: 12,
            plastic: 15,
            wood: 12,
        };
        const material = this.colorData.texture.material ?? '';
        this.sound_dieMaterial = /wood|metal/g.test(material) ? material : 'plastic';
        await this.loadSoundGroup(this.sounds_table, this.surface, surfaces[this.surface], s => `sounds/surfaces/surface_${this.surface}${s}.mp3`);
        await this.loadSoundGroup(this.sounds_dice, 'coin', dieMaterials['coin'], s => `sounds/dicehit/dicehit_coin${s}.mp3`);
        await this.loadSoundGroup(this.sounds_dice, this.sound_dieMaterial, dieMaterials[this.sound_dieMaterial], s => `sounds/dicehit/dicehit_${this.sound_dieMaterial}${s}.mp3`);
    }
    async loadSoundGroup(store, key, count, pathFor) {
        if (Object.hasOwn(store, key))
            return;
        store[key] = [];
        for (let s = 1; s <= count; ++s) {
            const clip = await this.loadAudio(this.assetPath + pathFor(s));
            if (clip)
                store[key].push(clip);
        }
    }
    loadAudio(src) {
        return new Promise(resolve => {
            const audio = new Audio();
            audio.crossOrigin = 'anonymous';
            audio.preload = 'auto';
            let settled = false;
            let timer;
            const finish = (value) => {
                if (settled)
                    return;
                settled = true;
                clearTimeout(timer);
                resolve(value);
            };
            timer = setTimeout(() => {
                console.warn(`[dice-engine] Audio load timed out, skipping: ${src}`);
                finish(undefined);
            }, AUDIO_LOAD_TIMEOUT_MS);
            audio.oncanplaythrough = () => finish(audio);
            audio.onerror = () => {
                console.error(`[dice-engine] Unable to load audio: ${src}`);
                finish(undefined);
            };
            audio.src = src;
            audio.load();
        });
    }
    async updateConfig(options = {}) {
        this.theme_customColorset = options.theme_customColorset ?? null;
        if (options.theme_colorset)
            this.theme_colorset = options.theme_colorset;
        if (options.theme_texture)
            this.theme_texture = options.theme_texture;
        if (options.theme_material)
            this.theme_material = options.theme_material;
        if (options.theme_colorset ||
            options.theme_texture ||
            options.theme_material ||
            options.theme_customColorset) {
            await this.loadTheme({
                colorset: this.theme_colorset,
                texture: this.theme_texture,
                material: this.theme_material,
            });
        }
    }
    setDimensions(dimensions) {
        this.display.currentWidth = this.container.clientWidth / 2;
        this.display.currentHeight = this.container.clientHeight / 2;
        if (dimensions) {
            this.display.containerWidth = dimensions.x;
            this.display.containerHeight = dimensions.y;
        }
        else {
            this.display.containerWidth = this.display.currentWidth;
            this.display.containerHeight = this.display.currentHeight;
        }
        this.display.aspect = Math.min(this.display.currentWidth / this.display.containerWidth, this.display.currentHeight / this.display.containerHeight);
        this.display.scale =
            Math.hypot(this.display.containerWidth, this.display.containerHeight) / 13;
        this.makeWorldBox();
        this.renderer.setSize(this.display.currentWidth * 2, this.display.currentHeight * 2);
        this.cameraHeight.max =
            this.display.currentHeight /
                this.display.aspect /
                Math.tan((10 * Math.PI) / 180);
        this.cameraHeight.medium = this.cameraHeight.max / 1.5;
        this.cameraHeight.far = this.cameraHeight.max;
        this.cameraHeight.close = this.cameraHeight.max / 2;
        if (this.camera)
            this.scene.remove(this.camera);
        this.camera = new THREE.PerspectiveCamera(20, this.display.currentWidth / this.display.currentHeight, 1, this.cameraHeight.max * 1.3);
        if (this.animstate === 'selector') {
            const count = this.selector.dice.length;
            if (count > 9)
                this.camera.position.z = this.cameraHeight.far;
            else if (count < 6)
                this.camera.position.z = this.cameraHeight.close;
            else
                this.camera.position.z = this.cameraHeight.medium;
        }
        else {
            this.camera.position.z = this.cameraHeight.far;
        }
        this.camera.lookAt(new THREE.Vector3(0, 0, 0));
        const maxwidth = Math.max(this.display.containerWidth, this.display.containerHeight);
        if (this.light)
            this.scene.remove(this.light);
        if (this.light_amb)
            this.scene.remove(this.light_amb);
        this.light = new THREE.SpotLight(this.color_spotlight, this.light_intensity);
        this.light.position.set(-maxwidth / 2, maxwidth / 2, maxwidth * 3);
        this.light.target.position.set(0, 0, 0);
        this.light.distance = maxwidth * 5;
        this.light.angle = Math.PI / 4;
        this.light.castShadow = this.shadows;
        this.light.shadow.camera.near = maxwidth / 10;
        this.light.shadow.camera.far = maxwidth * 5;
        this.light.shadow.camera.fov = 50;
        this.light.shadow.bias = 0.001;
        this.light.shadow.mapSize.width = 1024;
        this.light.shadow.mapSize.height = 1024;
        this.scene.add(this.light);
        this.light_amb = new THREE.HemisphereLight(0xffffbb, 0x676771, this.light_intensity);
        this.scene.add(this.light_amb);
        if (this.desk)
            this.scene.remove(this.desk);
        const shadowplane = new THREE.ShadowMaterial();
        shadowplane.opacity = 0.5;
        this.desk = new THREE.Mesh(new THREE.PlaneGeometry(this.display.containerWidth * 6, this.display.containerHeight * 6, 1, 1), shadowplane);
        this.desk.receiveShadow = this.shadows;
        this.scene.add(this.desk);
        this.renderer.render(this.scene, this.camera);
    }
    resizeWorld() {
        const resize = () => {
            const canvas = this.renderer.domElement;
            const width = this.container.clientWidth;
            const height = this.container.clientHeight;
            const needResize = canvas.width !== width || canvas.height !== height;
            if (needResize) {
                this.setDimensions(new THREE.Vector2(this.container.clientWidth, this.container.clientHeight));
            }
            return needResize;
        };
        let frame;
        this.onResizeBound = () => {
            if (frame)
                globalThis.cancelAnimationFrame(frame);
            frame = globalThis.requestAnimationFrame(resize);
        };
        globalThis.addEventListener('resize', this.onResizeBound);
    }
    vectorRand({ x, y }) {
        const angle = (Math.random() * Math.PI) / 5 - Math.PI / 5 / 2;
        const vec = {
            x: x * Math.cos(angle) - y * Math.sin(angle),
            y: x * Math.sin(angle) + y * Math.cos(angle),
        };
        if (vec.x === 0)
            vec.x = 0.01;
        if (vec.y === 0)
            vec.y = 0.01;
        return vec;
    }
    throwVectors(diceobj, vector, dist, boost) {
        const vec = this.vectorRand(vector);
        vec.x /= dist;
        vec.y /= dist;
        const pos = {
            x: this.display.containerWidth * (vec.x > 0 ? -1 : 1) * 0.9,
            y: this.display.containerHeight * (vec.y > 0 ? -1 : 1) * 0.9,
            z: Math.random() * 200 + 200,
        };
        const projector = Math.abs(vec.x / vec.y);
        if (projector > 1)
            pos.y /= projector;
        else
            pos.x *= projector;
        const velvec = this.vectorRand(vector);
        velvec.x /= dist;
        velvec.y /= dist;
        if (diceobj.shape !== 'd2') {
            return {
                pos,
                velocity: { x: velvec.x * boost, y: velvec.y * boost, z: -10 },
                angle: {
                    x: -(Math.random() * vec.y * 5 + diceobj.inertia * vec.y),
                    y: Math.random() * vec.x * 5 + diceobj.inertia * vec.x,
                    z: 0,
                },
                axis: {
                    x: Math.random(),
                    y: Math.random(),
                    z: Math.random(),
                    a: Math.random(),
                },
            };
        }
        // coin flip (d2)
        return {
            pos,
            velocity: { x: (velvec.x * boost) / 10, y: (velvec.y * boost) / 10, z: 3000 },
            angle: { x: 12 * diceobj.inertia, y: 1 * diceobj.inertia, z: 0 },
            axis: { x: 1, y: 1, z: Math.random(), a: Math.random() },
        };
    }
    getNotationVectors(notation, vector, boost, dist) {
        const notationVectors = new DiceNotation(notation);
        for (const i in notationVectors.set) {
            const set = notationVectors.set[i];
            const diceobj = this.DiceFactory.get(set.type);
            for (let k = 0; k < set.num; k++) {
                const { pos, velocity, angle, axis } = this.throwVectors(diceobj, vector, dist, boost);
                notationVectors.vectors.push({
                    index: this.dieIndex++,
                    type: diceobj.type,
                    op: set.op,
                    sid: set.sid,
                    gid: set.gid,
                    glvl: set.glvl,
                    func: set.func,
                    args: set.args,
                    pos,
                    velocity,
                    angle,
                    axis,
                });
            }
        }
        return notationVectors;
    }
    normalizeDieValue(type, value) {
        if (type === 'd10' && value === 0)
            return 10;
        if (type === 'd100' && value === 0)
            return 100;
        if (type === 'd100' && value > 0 && value < 10)
            return value * 10;
        return value;
    }
    swapDiceFace(dicemesh, result) {
        const diceobj = this.DiceFactory.get(dicemesh.notation.type);
        dicemesh.resultReason = 'forced';
        if (diceobj.shape === 'd4') {
            this.swapDiceFace_D4(dicemesh, result);
            return;
        }
        const type = dicemesh.notation.type;
        const value = this.normalizeDieValue(type, Number.parseInt(`${dicemesh.getLastValue().value}`));
        const target = this.normalizeDieValue(type, Number.parseInt(`${result}`));
        const valueindex = diceobj.values.indexOf(value);
        const resultindex = diceobj.values.indexOf(target);
        if (valueindex < 0 || resultindex < 0)
            return;
        if (valueindex === resultindex)
            return;
        const geom = dicemesh.geometry.clone();
        const magic = diceobj.shape === 'd10' ? 1 : 2;
        const material_value = diceobj.shape === 'd2' ? valueindex + 1 : valueindex + magic;
        const material_result = diceobj.shape === 'd2' ? resultindex + 1 : resultindex + magic;
        const geomindex_value = [];
        const geomindex_result = [];
        for (let i = 0, l = geom.groups.length; i < l; ++i) {
            const matindex = geom.groups[i].materialIndex;
            if (matindex === material_value)
                geomindex_value.push(i);
            else if (matindex === material_result)
                geomindex_result.push(i);
        }
        if (geomindex_value.length <= 0 || geomindex_result.length <= 0)
            return;
        for (const i of geomindex_result)
            geom.groups[i].materialIndex = material_value;
        for (const i of geomindex_value)
            geom.groups[i].materialIndex = material_result;
        dicemesh.geometry = geom;
        dicemesh.result = [];
    }
    swapDiceFace_D4(dicemesh, result) {
        const diceobj = this.DiceFactory.get(dicemesh.notation.type);
        const value = Number.parseInt(`${dicemesh.getLastValue().value}`);
        const resultValue = Number.parseInt(`${result}`);
        if (!(value >= 1 && value <= 4))
            return;
        let num = resultValue - value;
        const geom = dicemesh.geometry.clone();
        for (let i = 0, l = geom.groups.length; i < l; ++i) {
            const face = geom.groups[i];
            let matindex = face.materialIndex;
            if (matindex === undefined || matindex === 0)
                continue;
            matindex += num - 1;
            while (matindex > 4)
                matindex -= 4;
            while (matindex < 1)
                matindex += 4;
            face.materialIndex = matindex + 1;
        }
        if (num !== 0) {
            if (num < 0)
                num += 4;
            dicemesh.material = this.DiceFactory.createMaterials(diceobj, 0, 0, false, num);
        }
        dicemesh.geometry = geom;
    }
    applyForcedResults(notation, baseIndex) {
        if (!notation.result || notation.result.length === 0)
            return;
        for (let i = 0; i < notation.result.length; i++) {
            const dicemesh = this.diceList[baseIndex + i];
            if (!dicemesh)
                continue;
            if (`${dicemesh.getLastValue().value}` === `${notation.result[i]}`)
                continue;
            this.swapDiceFace(dicemesh, notation.result[i]);
        }
    }
    isDeterministic(notation) {
        return (notation.result?.length ?? 0) > 0;
    }
    setThrowGroup(deterministic) {
        if (!deterministic) {
            this.currentThrowGroup = DiceBox.NON_DET_GROUP;
            return;
        }
        this.throwGroupCounter = (this.throwGroupCounter + 1) % 29;
        this.currentThrowGroup = 1 << (this.throwGroupCounter + 2);
    }
    spawnDice(vectordata, reset = false) {
        const { pos, axis, angle, velocity } = vectordata;
        let dicemesh;
        if (reset) {
            dicemesh = reset;
            dicemesh.stopped = 0;
            this.world.removeBody(dicemesh.body);
        }
        else {
            const created = this.DiceFactory.create(vectordata.type);
            if (!created)
                return;
            dicemesh = created;
            dicemesh.notation = vectordata;
            dicemesh.result = [];
            dicemesh.stopped = 0;
            dicemesh.castShadow = this.shadows;
            this.scene.add(dicemesh);
            this.diceList.push(dicemesh);
        }
        dicemesh.body = new CANNON.Body({
            allowSleep: true,
            sleepSpeedLimit: 75,
            sleepTimeLimit: 0.9,
            mass: dicemesh.mass,
            shape: dicemesh.geometry.cannon_shape,
            material: this.dice_body_material,
            collisionFilterGroup: this.currentThrowGroup,
            collisionFilterMask: DiceBox.WALLS_GROUP | this.currentThrowGroup,
        });
        dicemesh.body.type = CANNON.Body.DYNAMIC;
        dicemesh.body.position.set(pos.x, pos.y, pos.z);
        dicemesh.body.quaternion.setFromAxisAngle(new CANNON.Vec3(axis.x, axis.y, axis.z), axis.a * Math.PI * 2);
        dicemesh.body.angularVelocity.set(angle.x, angle.y, angle.z);
        dicemesh.body.velocity.set(velocity.x, velocity.y, velocity.z);
        dicemesh.body.linearDamping = 0.1;
        dicemesh.body.angularDamping = 0.1;
        dicemesh.body.diceShape = dicemesh.shape;
        dicemesh.body.sleepState = 0;
        dicemesh.body.addEventListener('collide', this.eventCollide.bind(this));
        this.world.addBody(dicemesh.body);
    }
    eventCollide({ body, target }) {
        if (this.animstate === 'simulate' || !this.sounds || this.volume <= 0)
            return;
        const now = Date.now();
        const stepnumber = body.world?.stepnumber ?? 0;
        const currentSoundType = body.mass > 0 ? 'dice' : 'table';
        const tooSoon = this.lastSoundStep === stepnumber || this.lastSound > now;
        if (tooSoon && currentSoundType !== 'dice')
            return;
        if (tooSoon && currentSoundType === 'dice' && this.lastSoundType === 'dice') {
            return;
        }
        if (body.mass > 0) {
            this.playCollisionSound(body.velocity.length(), this.diceClip(body));
            this.lastSoundType = 'dice';
        }
        else {
            const list = this.sounds_table[this.surface];
            this.playCollisionSound(target.velocity.length(), this.randomClip(list));
            this.lastSoundType = 'table';
        }
        this.lastSoundStep = stepnumber;
        this.lastSound = now + this.soundDelay;
    }
    diceClip(body) {
        const list = body.diceShape === 'd2'
            ? this.sounds_dice['coin']
            : this.sounds_dice[this.sound_dieMaterial];
        return this.randomClip(list);
    }
    randomClip(list) {
        if (!list || list.length === 0)
            return undefined;
        return list[Math.floor(Math.random() * list.length)];
    }
    playCollisionSound(speed, sound) {
        if (speed < 250 || !sound)
            return;
        sound.volume = Math.min(speed / 8000, this.volume / 100);
        sound.play().catch(() => { });
    }
    checkForRethrow(_dicemesh) {
        return false;
    }
    isHeld(die) {
        return this.dragging === die || this.draggingPartner === die;
    }
    resolveDie(dicemesh, forcedFinish) {
        if (this.isHeld(dicemesh) && !forcedFinish)
            return 'awake';
        const sleepState = CANNON.Body.SLEEPING;
        if (dicemesh.body.sleepState < sleepState && !forcedFinish)
            return 'awake';
        if (dicemesh.body.type === CANNON.Body.KINEMATIC)
            return 'settled';
        let rethrow = false;
        if (dicemesh.result.length === 0) {
            dicemesh.storeRolledValue(dicemesh.resultReason);
            rethrow = this.checkForRethrow(dicemesh);
        }
        else if (dicemesh.rerolling) {
            dicemesh.rerolling = false;
            dicemesh.storeRolledValue('reroll');
            rethrow = this.checkForRethrow(dicemesh);
        }
        if (rethrow) {
            dicemesh.rerolls += 1;
            dicemesh.rerolling = true;
            dicemesh.body.wakeUp();
            dicemesh.body.type = CANNON.Body.DYNAMIC;
            dicemesh.body.angularVelocity = new CANNON.Vec3(25, 25, 25);
            dicemesh.body.velocity = new CANNON.Vec3(0, 0, 3000);
            return 'rethrow';
        }
        dicemesh.rerolling = false;
        dicemesh.body.type = CANNON.Body.KINEMATIC;
        return 'settled';
    }
    scheduleFrame(timeDiff, run) {
        if (!this.adaptive_timestep && timeDiff < this.framerate) {
            setTimeout(() => requestAnimationFrame(run), (this.framerate - timeDiff) * 1000);
        }
        else {
            requestAnimationFrame(run);
        }
    }
    animateThrow(threadid) {
        this.animstate = 'throw';
        const time = Date.now();
        this.last_time = this.last_time || time - this.framerate * 1000;
        const time_diff = (time - this.last_time) / 1000;
        ++this.iteration;
        const neededSteps = Math.floor(time_diff / this.framerate);
        for (let i = 0; i < neededSteps; i++) {
            this.world.step(this.framerate);
            ++this.steps;
        }
        for (const die of this.diceList) {
            const { position, quaternion } = die.body;
            die.position.set(position.x, position.y, position.z);
            die.quaternion.set(quaternion.x, quaternion.y, quaternion.z, quaternion.w);
        }
        this.last_time = this.last_time + neededSteps * this.framerate * 1000;
        if (this.running === threadid) {
            this.serviceGroups(time);
            this.updateSettledState();
        }
        this.renderer.render(this.scene, this.camera);
        if (this.running !== threadid)
            return;
        if (this.throwGroups.length === 0) {
            this.running = false;
            this.rolling = false;
            this.animstate = 'afterthrow';
            if (this.diceList.length === 0)
                this.onEmpty();
            this.renderer.render(this.scene, this.camera);
            return;
        }
        this.scheduleFrame(time_diff, () => this.animateThrow(threadid));
    }
    serviceGroups(now) {
        const forcedFinish = this.iteration > this.iterationLimit;
        this.throwGroups = this.throwGroups.filter(group => this.serviceGroup(group, now, forcedFinish));
    }
    updateSettledState() {
        const atRest = this.diceList.length > 0 &&
            this.dragging === null &&
            this.diceList.every(die => this.isSelectableDie(die));
        if (atRest === this.tableAtRest)
            return;
        this.tableAtRest = atRest;
        if (!atRest)
            return;
        const results = this.diceList.map((die, id) => this.dieResult(die, id));
        this.onSettled(results);
        this.dispatchDiceEvent('diceSettled', results);
    }
    serviceGroup(group, now, forcedFinish) {
        if (group.settledAt === null) {
            if (!this.groupSettled(group, forcedFinish))
                return true;
            group.settledAt = now;
            if (!group.resolved) {
                group.resolved = true;
                group.resolve();
            }
        }
        if (this.dragging && group.dice.includes(this.dragging)) {
            group.settledAt = null;
            return true;
        }
        return this.serviceRemoval(group, now, group.settledAt);
    }
    serviceRemoval(group, now, settledAt) {
        if (group.removal.style === 'none') {
            for (const die of group.dice)
                this.recordPlacement(die);
            return false;
        }
        if (group.removal.style === 'reset') {
            if (now - settledAt < group.removal.dwellMs)
                return true;
            for (const die of group.dice)
                this.resetToPlacement(die);
            return false;
        }
        return this.serviceExit(group, now, settledAt);
    }
    serviceExit(group, now, settledAt) {
        if (!group.exiting && now - settledAt >= group.removal.dwellMs) {
            group.exiting = true;
            group.exitStart = now;
            for (const die of group.dice)
                die.body.collisionResponse = false;
        }
        if (!group.exiting)
            return true;
        const progress = Math.min((now - group.exitStart) / group.removal.durationMs, 1);
        this.applyExit(group.dice, group.removal.style, progress);
        if (progress < 1)
            return true;
        for (const die of group.dice)
            this.removeDie(die);
        return false;
    }
    groupSettled(group, forcedFinish) {
        for (const die of group.dice) {
            if (this.resolveDie(die, forcedFinish) !== 'settled')
                return false;
        }
        return true;
    }
    ensureAnimating() {
        if (this.running !== false)
            return;
        this.animstate = 'throw';
        this.rolling = true;
        this.last_time = 0;
        this.running = Date.now();
        this.animateThrow(this.running);
    }
    startClickThrow(notation) {
        const vector = {
            x: (Math.random() * 2 - 0.5) * this.display.currentWidth,
            y: -(Math.random() * 2 - 0.5) * this.display.currentHeight,
        };
        const dist = Math.hypot(vector.x, vector.y) + 100;
        const boost = (Math.random() + 3) * dist * this.strength;
        return this.getNotationVectors(notation, vector, boost, dist);
    }
    clearHover() {
        if (!this.hoveredDice)
            return;
        this.hoveredDice = null;
        this.onDiceHover(null);
        this.dispatchDiceEvent('diceHover', null);
    }
    // Remove dice resting below a normalized y (the bottom/tray zone), leaving the
    // rest in place. Used to restock a tray without disturbing a separate top zone.
    clearBelow(normalizedY) {
        const worldY = normalizedY * this.display.containerHeight * 0.9;
        const removed = this.diceList.filter(die => die.body.position.y < worldY);
        if (removed.length === 0)
            return;
        this.detachFromGroups(removed);
        for (const die of removed) {
            if (this.dragging === die)
                this.dragging = null;
            if (this.draggingPartner === die)
                this.draggingPartner = null;
            this.removeDie(die);
        }
        this.renderer.render(this.scene, this.camera);
    }
    clearDice() {
        this.running = false;
        this.dragging = null;
        this.draggingPartner = null;
        this.carriedUnits = [];
        this.carriedOffset.clear();
        this.clearHover();
        this.cancelGroups();
        let dice;
        while ((dice = this.diceList.pop())) {
            this.scene.remove(dice);
            if (dice.body)
                this.world.removeBody(dice.body);
        }
        this.renderer.render(this.scene, this.camera);
        setTimeout(() => {
            if (!this.disposed)
                this.renderer.render(this.scene, this.camera);
        }, 100);
    }
    /**
     * Tear the box down: stop the loop, drop all dice, detach listeners and the
     * canvas, and release the WebGL context. Used when a renderer is unmounted so
     * navigating between views does not leak canvases/listeners or stale dice.
     */
    dispose() {
        this.disposed = true;
        this.running = false;
        this.rolling = false;
        this.teardownSelection();
        if (this.onResizeBound) {
            globalThis.removeEventListener('resize', this.onResizeBound);
            this.onResizeBound = undefined;
        }
        this.clearDice();
        this.renderer?.domElement?.remove();
        this.renderer?.dispose();
    }
    resolveRemoval(removal) {
        const d = DiceBox.DEFAULT_REMOVAL;
        return {
            style: removal?.style ?? d.style,
            dwellMs: removal?.dwellMs ?? d.dwellMs,
            durationMs: removal?.durationMs ?? d.durationMs,
        };
    }
    applyExit(dice, style, progress) {
        if (style === 'fade') {
            const opacity = Math.max(1 - progress, 0);
            for (const die of dice) {
                for (const mat of die.material)
                    mat.opacity = opacity;
            }
        }
        else {
            const scale = Math.max(1 - progress, 0.0001);
            for (const die of dice)
                die.scale.setScalar(scale);
        }
    }
    removeDie(die) {
        if (this.hoveredDice === die)
            this.clearHover();
        const index = this.diceList.indexOf(die);
        if (index !== -1)
            this.diceList.splice(index, 1);
        this.scene.remove(die);
        if (die.body)
            this.world.removeBody(die.body);
    }
    recordPlacement(die) {
        const p = die.body.position;
        const q = die.body.quaternion;
        die.placement = {
            position: { x: p.x, y: p.y, z: p.z },
            quaternion: { x: q.x, y: q.y, z: q.z, w: q.w },
        };
    }
    resetToPlacement(die) {
        const placement = die.placement;
        if (!placement)
            return;
        const { position, quaternion } = placement;
        die.rerolling = false;
        die.scale.setScalar(1);
        for (const mat of die.material)
            mat.opacity = 1;
        die.body.type = CANNON.Body.KINEMATIC;
        die.body.velocity.setZero();
        die.body.angularVelocity.setZero();
        die.body.position.set(position.x, position.y, position.z);
        die.body.quaternion.set(quaternion.x, quaternion.y, quaternion.z, quaternion.w);
        die.body.sleep();
        die.position.set(position.x, position.y, position.z);
        die.quaternion.set(quaternion.x, quaternion.y, quaternion.z, quaternion.w);
    }
    cancelGroups() {
        for (const group of this.throwGroups) {
            for (const die of group.dice) {
                if (!this.diceList.includes(die))
                    continue;
                die.scale.setScalar(1);
                for (const mat of die.material)
                    mat.opacity = 1;
                die.body.collisionResponse = true;
            }
            if (!group.resolved) {
                group.resolved = true;
                group.resolve();
            }
        }
        this.throwGroups = [];
    }
    dieResult(die, id) {
        const last = die.result.at(-1);
        return {
            type: die.shape,
            sides: Number.parseInt(die.shape.substring(1)),
            id,
            dieId: die.notation.index,
            value: last?.value ?? 0,
            label: last?.label,
            reason: last?.reason ?? 'unsettled',
        };
    }
    // Link the tens (`d100`) and ones (`d10`) dice of each percentile in a throw
    // so a grab/flick picks up and rerolls both together. The core emits
    // `Nd100+Nd10` (tens first, then ones), so the j-th tens pairs with the j-th
    // ones; any leftover standalone d10s are left unpaired.
    linkPercentilePairs(dice) {
        const tens = dice.filter(die => die.notation.type === 'd100');
        const ones = dice.filter(die => die.notation.type === 'd10');
        const pairs = Math.min(tens.length, ones.length);
        for (let i = 0; i < pairs; i++) {
            tens[i].percentilePartner = ones[i];
            ones[i].percentilePartner = tens[i];
        }
    }
    // Fold a tens face (10..100, 100 = "00") and a ones face (1..10, 10 = "0")
    // into a 1-100 percentile value, matching the core's combineD100.
    combineD100(tens, ones) {
        const value = (tens % 100) + (ones % 10);
        return value === 0 ? 100 : value;
    }
    buildDiceEventData(die) {
        const result = this.dieResult(die, this.diceList.indexOf(die));
        const { x, y, z } = die.position;
        return {
            ...result,
            position: { x, y, z },
            screenPosition: this.getScreenPosition(die.position),
            scale: die.scale.x,
        };
    }
    getScreenPosition(position) {
        const rect = this.renderer.domElement.getBoundingClientRect();
        const projected = position.clone().project(this.camera);
        return {
            x: (projected.x * 0.5 + 0.5) * rect.width,
            y: (-projected.y * 0.5 + 0.5) * rect.height,
        };
    }
    dispatchDiceEvent(name, detail) {
        document.dispatchEvent(new CustomEvent(name, { detail }));
    }
    isSelectableDie(die) {
        return (this.diceList.includes(die) && die.result.length > 0 && !die.rerolling);
    }
    isGrabbableDie(die) {
        if (!die.flickable)
            return false;
        return this.isSelectableDie(die)
            ? die.flickOnSettled
            : this.diceList.includes(die);
    }
    buildGrabEventData(die) {
        const partner = die.percentilePartner;
        if (partner && this.diceList.includes(partner)) {
            return this.buildPercentileGrabData(die, partner);
        }
        const face = die.getFaceValue();
        const { x, y, z } = die.position;
        return {
            type: die.shape,
            sides: Number.parseInt(die.shape.slice(1)),
            id: this.diceList.indexOf(die),
            dieId: die.notation.index,
            value: face.value,
            label: face.label,
            reason: 'grabbed',
            position: { x, y, z },
            screenPosition: this.getScreenPosition(die.position),
            scale: die.scale.x,
        };
    }
    buildPercentileGrabData(die, partner) {
        const tens = die.notation.type === 'd100' ? die : partner;
        const ones = die.notation.type === 'd100' ? partner : die;
        const value = this.combineD100(tens.getFaceValue().value, ones.getFaceValue().value);
        const { x, y, z } = die.position;
        return {
            type: 'd100',
            sides: 100,
            id: this.diceList.indexOf(die),
            dieId: tens.notation.index,
            value,
            label: `${value}`,
            reason: 'grabbed',
            position: { x, y, z },
            screenPosition: this.getScreenPosition(die.position),
            scale: die.scale.x,
        };
    }
    onMouseMove(event) {
        if (!this.enableDiceSelection ||
            this.dragging ||
            this.diceList.length === 0)
            return;
        const { raycaster, mouse } = this;
        if (!raycaster || !mouse)
            return;
        const rect = this.renderer.domElement.getBoundingClientRect();
        mouse.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
        mouse.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;
        raycaster.setFromCamera(mouse, this.camera);
        const hit = raycaster
            .intersectObjects(this.diceList)
            .map(intersection => intersection.object)
            .find(die => this.isSelectableDie(die));
        if (hit) {
            if (this.hoveredDice !== hit) {
                this.hoveredDice = hit;
                const data = this.buildDiceEventData(hit);
                this.onDiceHover(data);
                this.dispatchDiceEvent('diceHover', data);
            }
        }
        else if (this.hoveredDice) {
            this.hoveredDice = null;
            this.onDiceHover(null);
            this.dispatchDiceEvent('diceHover', null);
        }
    }
    onMouseClick(event) {
        if (!this.enableDiceSelection ||
            !this.hoveredDice ||
            !this.isSelectableDie(this.hoveredDice)) {
            return;
        }
        event.preventDefault();
        event.stopPropagation();
        const data = this.buildDiceEventData(this.hoveredDice);
        this.onDiceClick(data);
        this.dispatchDiceEvent('diceClick', data);
    }
    pointerNdc(clientX, clientY) {
        const ndc = this.dragNdc;
        const rect = this.renderer.domElement.getBoundingClientRect();
        ndc.x = ((clientX - rect.left) / rect.width) * 2 - 1;
        ndc.y = -((clientY - rect.top) / rect.height) * 2 + 1;
        return ndc;
    }
    pickDie(clientX, clientY) {
        const raycaster = this.raycaster;
        if (!raycaster)
            return undefined;
        raycaster.setFromCamera(this.pointerNdc(clientX, clientY), this.camera);
        return raycaster
            .intersectObjects(this.diceList)
            .map(intersection => intersection.object)
            .find(die => this.isGrabbableDie(die));
    }
    pointerToTable(clientX, clientY) {
        const raycaster = this.raycaster;
        const plane = this.tablePlane;
        if (!raycaster || !plane)
            return null;
        raycaster.setFromCamera(this.pointerNdc(clientX, clientY), this.camera);
        const hit = raycaster.ray.intersectPlane(plane, new THREE.Vector3());
        return hit ? { x: hit.x, y: hit.y } : null;
    }
    grabPercentilePartner(die) {
        let partner = die.percentilePartner;
        if (!partner || !this.diceList.includes(partner)) {
            // A lone placed d100 (the tens die) has no ones die yet; spawn and link one
            // so grabbing/flicking it rolls a full percentile, not just the tens.
            partner =
                die.notation.type === 'd100'
                    ? this.spawnPercentileOnes(die)
                    : undefined;
        }
        if (!partner || !this.diceList.includes(partner))
            return;
        const partnerInMotion = !this.isSelectableDie(partner);
        this.draggingPartner = partner;
        this.dragPartnerOffset = { x: this.dieRadius(die) + this.dieRadius(partner), y: 0 };
        partner.rerolling = false;
        partner.body.type = CANNON.Body.KINEMATIC;
        partner.body.velocity.setZero();
        partner.body.angularVelocity.setZero();
        if (partnerInMotion)
            partner.storeRolledValue('grabbed');
        const px = die.body.position.x + this.dragPartnerOffset.x;
        const py = die.body.position.y + this.dragPartnerOffset.y;
        partner.body.position.set(px, py, this.dragRestZ);
        partner.position.set(px, py, this.dragRestZ);
        this.renderer.render(this.scene, this.camera);
    }
    // Spawn a ones (`d10`) die and pair it with a tens (`d100`) die, so a placed
    // percentile that started life as a lone tens can be grabbed/flicked as a full
    // percentile. Mirrors spawnCarriedUnit's spawn setup; grabPercentilePartner
    // then positions the ones beside the tens.
    spawnPercentileOnes(tens) {
        const throwNotation = this.startClickThrow('1d10');
        if (!throwNotation ||
            throwNotation.error ||
            throwNotation.vectors.length === 0) {
            return undefined;
        }
        const existing = this.diceList.length;
        this.setThrowGroup(false);
        for (const vectordata of throwNotation.vectors)
            this.spawnDice(vectordata);
        const ones = this.diceList[existing];
        if (!ones)
            return undefined;
        ones.flickable = this.enableDiceDrag;
        ones.flickOnSettled = this.enableDiceDrag;
        ones.rerolling = false;
        ones.body.type = CANNON.Body.KINEMATIC;
        ones.body.velocity.setZero();
        ones.body.angularVelocity.setZero();
        tens.percentilePartner = ones;
        ones.percentilePartner = tens;
        return ones;
    }
    dieRadius(die) {
        if (!die.geometry.boundingSphere)
            die.geometry.computeBoundingSphere();
        const radius = die.geometry.boundingSphere?.radius ?? this.baseScale * 0.45;
        return radius * die.scale.x;
    }
    onPointerDown(event) {
        if (!this.enableDiceDrag || event.button !== 0 || this.diceList.length === 0)
            return;
        const die = this.pickDie(event.clientX, event.clientY);
        if (!die)
            return;
        event.preventDefault();
        event.stopPropagation();
        const inMotion = !this.isSelectableDie(die);
        this.dragging = die;
        this.dragRestZ = die.body.position.z;
        const point = this.pointerToTable(event.clientX, event.clientY);
        this.dragSamples = point
            ? [{ x: point.x, y: point.y, t: event.timeStamp }]
            : [];
        die.rerolling = false;
        die.body.type = CANNON.Body.KINEMATIC;
        die.body.velocity.setZero();
        die.body.angularVelocity.setZero();
        if (inMotion)
            die.storeRolledValue('grabbed');
        this.grabPercentilePartner(die);
        const grabData = this.buildGrabEventData(die);
        this.onDiceGrabbed(grabData);
        this.dispatchDiceEvent('diceGrabbed', grabData);
        if (this.hoveredDice) {
            this.hoveredDice = null;
            this.onDiceHover(null);
            this.dispatchDiceEvent('diceHover', null);
        }
    }
    onPointerMove(event) {
        const die = this.dragging;
        if (!die)
            return;
        event.preventDefault();
        event.stopPropagation();
        const point = this.pointerToTable(event.clientX, event.clientY);
        if (!point)
            return;
        die.body.position.set(point.x, point.y, this.dragRestZ);
        die.position.set(point.x, point.y, this.dragRestZ);
        const partner = this.draggingPartner;
        if (partner) {
            const px = point.x + this.dragPartnerOffset.x;
            const py = point.y + this.dragPartnerOffset.y;
            partner.body.position.set(px, py, this.dragRestZ);
            partner.position.set(px, py, this.dragRestZ);
        }
        if (this.carriedUnits.length > 0)
            this.placeCarriedAround(point.x, point.y);
        this.dragSamples.push({ x: point.x, y: point.y, t: event.timeStamp });
        if (this.dragSamples.length > 6)
            this.dragSamples.shift();
        this.renderer.render(this.scene, this.camera);
    }
    onPointerUp(event) {
        const die = this.dragging;
        const partner = this.draggingPartner;
        if (!die)
            return;
        event.preventDefault();
        event.stopPropagation();
        this.dragging = null;
        this.draggingPartner = null;
        const flick = this.flickVelocity(this.dragSamples);
        this.dragSamples = [];
        this.releaseCarried(flick);
        const ids = [this.diceList.indexOf(die)];
        if (partner) {
            const partnerId = this.diceList.indexOf(partner);
            if (partnerId >= 0)
                ids.push(partnerId);
        }
        if (ids[0] < 0)
            return;
        const removal = this.dragRemoval;
        void (flick
            ? this.reroll(ids, {
                velocity: { x: flick.x, y: flick.y, z: DRAG_LAUNCH_Z },
                removal,
            })
            : this.reroll(ids, { removal }));
    }
    onContextMenu(event) {
        if (!this.dragging)
            return;
        event.preventDefault();
        event.stopPropagation();
        this.addCarried(this.dragging);
    }
    addCarried(held) {
        const isPercentile = held.percentilePartner !== undefined || held.notation.type === 'd100';
        const notation = isPercentile ? '1d100+1d10' : `1${held.notation.type}`;
        const unit = this.spawnCarriedUnit(notation);
        if (unit.length === 0)
            return;
        this.carriedUnits.push(unit);
        this.layoutCarried();
        this.renderer.render(this.scene, this.camera);
    }
    spawnCarriedUnit(notationString) {
        const throwNotation = this.startClickThrow(notationString);
        if (!throwNotation || throwNotation.error || throwNotation.vectors.length === 0) {
            return [];
        }
        const existing = this.diceList.length;
        this.setThrowGroup(false);
        for (const vectordata of throwNotation.vectors)
            this.spawnDice(vectordata);
        const unit = this.diceList.slice(existing);
        for (const die of unit) {
            die.flickable = this.enableDiceDrag;
            die.flickOnSettled = this.enableDiceDrag;
            die.rerolling = false;
            die.body.type = CANNON.Body.KINEMATIC;
            die.body.velocity.setZero();
            die.body.angularVelocity.setZero();
        }
        this.linkPercentilePairs(unit);
        return unit;
    }
    layoutCarried() {
        const held = this.dragging;
        if (!held)
            return;
        const count = this.carriedUnits.length;
        if (count === 0)
            return;
        const r = this.dieRadius(held);
        const slotArc = r * 2.4;
        let placed = 0;
        let ring = 0;
        while (placed < count) {
            const radius = r * 3 + ring * slotArc;
            const capacity = Math.max(1, Math.floor((2 * Math.PI * radius) / slotArc));
            const inRing = Math.min(capacity, count - placed);
            for (let j = 0; j < inRing; j++) {
                const angle = (2 * Math.PI * j) / inRing;
                this.placeCarriedUnit(this.carriedUnits[placed + j], radius, angle, r);
            }
            placed += inRing;
            ring++;
        }
        const { x, y } = held.body.position;
        this.placeCarriedAround(x, y);
    }
    placeCarriedUnit(unit, radius, angle, r) {
        const cx = Math.cos(angle) * radius;
        const cy = Math.sin(angle) * radius;
        if (unit.length === 1) {
            this.carriedOffset.set(unit[0], { x: cx, y: cy });
            return;
        }
        const tx = -Math.sin(angle) * r;
        const ty = Math.cos(angle) * r;
        this.carriedOffset.set(unit[0], { x: cx + tx, y: cy + ty });
        this.carriedOffset.set(unit[1], { x: cx - tx, y: cy - ty });
    }
    placeCarriedAround(centerX, centerY) {
        const z = this.dragRestZ + CARRY_LIFT;
        for (const unit of this.carriedUnits) {
            for (const die of unit) {
                const off = this.carriedOffset.get(die);
                if (!off)
                    continue;
                die.body.position.set(centerX + off.x, centerY + off.y, z);
                die.position.set(centerX + off.x, centerY + off.y, z);
            }
        }
    }
    releaseCarried(flick) {
        const units = this.carriedUnits;
        this.carriedUnits = [];
        this.carriedOffset.clear();
        if (units.length === 0)
            return;
        const removal = this.resolveRemoval(this.dragRemoval);
        for (const unit of units) {
            for (const die of unit) {
                die.scale.setScalar(1);
                die.body.collisionResponse = true;
                die.body.wakeUp();
                die.body.type = CANNON.Body.DYNAMIC;
                die.body.angularVelocity = new CANNON.Vec3(25, 25, 25);
                die.body.velocity = flick
                    ? new CANNON.Vec3(flick.x, flick.y, DRAG_LAUNCH_Z)
                    : new CANNON.Vec3(0, 0, 0);
            }
            this.throwGroups.push(this.makeGroup(unit, removal, () => {
                const results = unit.map(die => this.dieResult(die, this.diceList.indexOf(die)));
                this.onDiceAdded(results);
                this.dispatchDiceEvent('diceAdded', results);
            }));
        }
        this.iteration = 0;
        this.last_time = 0;
        this.ensureAnimating();
    }
    flickVelocity(samples) {
        if (samples.length < 2)
            return null;
        const first = samples[0];
        const last = samples.at(-1);
        if (Math.hypot(last.x - first.x, last.y - first.y) < DRAG_MOVE_THRESHOLD) {
            return null;
        }
        const dt = Math.max((last.t - first.t) / 1000, 1 / 120);
        let vx = ((last.x - first.x) / dt) * DRAG_GAIN;
        let vy = ((last.y - first.y) / dt) * DRAG_GAIN;
        const speed = Math.hypot(vx, vy);
        if (speed > DRAG_MAX_SPEED) {
            const scale = DRAG_MAX_SPEED / speed;
            vx *= scale;
            vy *= scale;
        }
        return { x: vx, y: vy };
    }
    getDiceResults(id) {
        if (id !== undefined) {
            return this.dieResult(this.diceList[id], id);
        }
        const notation = this.notationVectors;
        const modifier = notation.constant
            ? Number.parseInt(`${notation.op}${notation.constant}`)
            : 0;
        let counter = 0;
        let rollTotal = modifier;
        const sets = notation.set.map(set => {
            const endCount = counter + set.num - 1;
            let setTotal = 0;
            const rolls = [];
            for (let index = counter; index <= endCount; index++) {
                const die = this.diceList[counter];
                const last = die?.result.at(-1);
                if (!last || last.reason === 'remove') {
                    counter++;
                    continue;
                }
                rolls.push({
                    type: set.type,
                    sides: Number.parseInt(set.type.substring(1)),
                    id: counter,
                    dieId: die.notation.index,
                    value: last.value,
                    label: last.label,
                    reason: last.reason,
                });
                setTotal += last.value;
                counter++;
            }
            rollTotal += setTotal;
            return {
                num: set.num,
                type: set.type,
                sides: Number.parseInt(set.type.substring(1)),
                rolls,
                total: setTotal,
            };
        });
        return { notation: notation.notation, sets, modifier, total: rollTotal };
    }
    async roll(notationString, options = {}) {
        return this.add(notationString, options);
    }
    // Place a single die at a normalized (-1..1) table coordinate, resting flat
    // with `value` showing up. Synchronous (no tumble): the die is settled in
    // place, its up-face swapped to `value`, then frozen. `grabbable` only takes
    // effect when the box has `enableDiceDrag`. When `orientation` (degrees, yaw
    // about the vertical axis) is given, the drop is deterministic and the die is
    // spun to that yaw, so the same options always reproduce the same pose.
    place(options) {
        const { type, value, x, y, grabbable, orientation } = options;
        const throwNotation = this.startClickThrow(`1${type}`);
        if (!throwNotation || throwNotation.error || throwNotation.vectors.length === 0) {
            return undefined;
        }
        const fixedPose = typeof orientation === 'number';
        const wx = x * this.display.containerWidth * 0.9;
        const wy = y * this.display.containerHeight * 0.9;
        const vector = throwNotation.vectors[0];
        vector.pos = { x: wx, y: wy, z: 200 };
        vector.velocity = { x: 0, y: 0, z: 0 };
        // A fixed pose drops from a fixed tilt with no spin, so the synchronous settle
        // is reproducible; otherwise keep the lively random tumble.
        vector.angle = fixedPose
            ? { x: 0, y: 0, z: 0 }
            : { x: Math.random() * 2, y: Math.random() * 2, z: Math.random() * 2 };
        if (fixedPose)
            vector.axis = { x: 1, y: 0.7, z: 0.3, a: 0.1 };
        const existing = this.diceList.length;
        this.setThrowGroup(false);
        this.spawnDice(vector);
        const die = this.diceList[existing];
        if (!die)
            return undefined;
        const flickable = !!grabbable && this.enableDiceDrag;
        die.flickable = flickable;
        die.flickOnSettled = flickable;
        this.simulateAddedDice(existing);
        this.swapDiceFace(die, value);
        die.storeRolledValue('placed');
        // Spin the settled (flat) die about the vertical axis to the requested yaw;
        // this keeps the up-face up and only rotates how the die reads.
        if (fixedPose && orientation !== 0) {
            const yaw = new CANNON.Quaternion();
            yaw.setFromAxisAngle(new CANNON.Vec3(0, 0, 1), (orientation * Math.PI) / 180);
            yaw.mult(die.body.quaternion, die.body.quaternion);
        }
        const z = die.body.position.z;
        const q = die.body.quaternion;
        die.rerolling = false;
        die.body.type = CANNON.Body.KINEMATIC;
        die.body.velocity.setZero();
        die.body.angularVelocity.setZero();
        die.body.position.set(wx, wy, z);
        die.position.set(wx, wy, z);
        die.quaternion.set(q.x, q.y, q.z, q.w);
        this.recordPlacement(die);
        this.animstate = 'afterthrow';
        this.steps = 0;
        this.iteration = 0;
        this.renderer.render(this.scene, this.camera);
        return this.dieResult(die, existing);
    }
    async add(notationString, options = {}) {
        const { theme, removal, onSpawned, enableFlickOnSettled } = options;
        this.ensureSoundsLoaded();
        const removalSpec = this.resolveRemoval(removal);
        await this.applyThemeForThrow(theme);
        const existing = this.diceList.length;
        const throwNotation = this.startClickThrow(notationString);
        if (!throwNotation ||
            throwNotation.error ||
            throwNotation.vectors.length === 0) {
            if (!existing)
                this.notationVectors = throwNotation ?? null;
            onSpawned?.();
            return undefined;
        }
        if (options.center) {
            const spread = this.baseScale * 0.9;
            throwNotation.vectors.forEach((vector, i) => {
                vector.pos = { x: i * spread, y: 0, z: 220 };
                vector.velocity = { x: 0, y: 0, z: 0 };
                vector.angle = {
                    x: Math.random() * 3,
                    y: Math.random() * 3,
                    z: Math.random() * 3,
                };
            });
        }
        const deterministic = this.isDeterministic(throwNotation);
        this.setThrowGroup(deterministic);
        for (const vectordata of throwNotation.vectors)
            this.spawnDice(vectordata);
        const groupDice = this.diceList.slice(existing);
        const flickable = this.enableDiceDrag && !deterministic;
        const flickOnSettled = flickable && enableFlickOnSettled === true;
        for (const die of groupDice) {
            die.flickable = flickable;
            die.flickOnSettled = flickOnSettled;
        }
        this.linkPercentilePairs(groupDice);
        if (deterministic) {
            this.simulateAddedDice(existing);
            this.steps = 0;
            this.iteration = 0;
            throwNotation.vectors.forEach((vectordata, i) => {
                const die = this.diceList[existing + i];
                if (die)
                    this.spawnDice(vectordata, die);
            });
            this.applyForcedResults(throwNotation, existing);
            for (const die of groupDice)
                die.body?.wakeUp();
        }
        else {
            this.steps = 0;
            this.iteration = 0;
        }
        const isFresh = existing === 0;
        this.notationVectors = isFresh
            ? throwNotation
            : DiceNotation.mergeNotation(this.notationVectors, throwNotation);
        return new Promise(resolve => {
            this.throwGroups.push(this.makeGroup(groupDice, removalSpec, () => resolve(this.reportThrow(groupDice, isFresh))));
            this.ensureAnimating();
            onSpawned?.();
        });
    }
    async reroll(diceIdArray, options = {}) {
        this.iteration = 0;
        this.last_time = 0;
        const dice = diceIdArray
            .map(id => this.diceList[id])
            .filter((die) => Boolean(die));
        if (dice.length === 0)
            return [];
        this.detachFromGroups(dice);
        const velocity = options.velocity ?? { x: 0, y: 0, z: 3000 };
        const angular = options.angular ?? { x: 25, y: 25, z: 25 };
        for (const die of dice) {
            die.scale.setScalar(1);
            for (const mat of die.material)
                mat.opacity = 1;
            die.rerolls += 1;
            die.rerolling = true;
            die.body.collisionResponse = true;
            die.body.wakeUp();
            die.body.type = CANNON.Body.DYNAMIC;
            if (options.position) {
                die.body.position.set(options.position.x, options.position.y, options.position.z);
            }
            die.body.angularVelocity = new CANNON.Vec3(angular.x, angular.y, angular.z);
            die.body.velocity = new CANNON.Vec3(velocity.x, velocity.y, velocity.z);
        }
        return new Promise(resolve => {
            this.throwGroups.push(this.makeGroup(dice, this.resolveRemoval(options.removal), () => {
                const results = dice.map(die => this.dieResult(die, this.diceList.indexOf(die)));
                this.onRerollComplete(results);
                document.dispatchEvent(new CustomEvent('rerollComplete', { detail: results }));
                resolve(results);
            }));
            this.ensureAnimating();
        });
    }
    detachFromGroups(dice) {
        const detaching = new Set(dice);
        this.throwGroups = this.throwGroups.filter(group => {
            group.dice = group.dice.filter(die => !detaching.has(die));
            if (group.dice.length > 0)
                return true;
            if (!group.resolved) {
                group.resolved = true;
                group.resolve();
            }
            return false;
        });
    }
    makeGroup(dice, removal, resolve) {
        return {
            dice,
            resolve,
            resolved: false,
            removal,
            settledAt: null,
            exiting: false,
            exitStart: 0,
        };
    }
    reportThrow(dice, isFresh) {
        const results = dice.map(die => this.dieResult(die, this.diceList.indexOf(die)));
        this.onAddDiceComplete(results);
        document.dispatchEvent(new CustomEvent('addDiceComplete', { detail: results }));
        if (isFresh)
            this.announceRollComplete();
        return results;
    }
    announceRollComplete() {
        try {
            const results = this.getDiceResults();
            this.onRollComplete(results);
            document.dispatchEvent(new CustomEvent('rollComplete', { detail: results }));
        }
        catch { }
    }
    simulateAddedDice(startIndex) {
        const frozen = this.diceList.slice(0, startIndex).map(die => ({
            die,
            type: die.body.type,
            position: die.body.position.clone(),
            quaternion: die.body.quaternion.clone(),
            velocity: die.body.velocity.clone(),
            angularVelocity: die.body.angularVelocity.clone(),
            sleepState: die.body.sleepState,
        }));
        for (const { die } of frozen) {
            die.body.type = CANNON.Body.KINEMATIC;
            die.body.velocity.setZero();
            die.body.angularVelocity.setZero();
        }
        this.animstate = 'simulate';
        this.iteration = 0;
        while (!this.addedDiceSettled(startIndex)) {
            ++this.iteration;
            this.world.step(this.framerate);
        }
        for (const f of frozen) {
            f.die.body.type = f.type;
            f.die.body.position.copy(f.position);
            f.die.body.quaternion.copy(f.quaternion);
            f.die.body.velocity.copy(f.velocity);
            f.die.body.angularVelocity.copy(f.angularVelocity);
            f.die.body.sleepState = f.sleepState;
        }
    }
    addedDiceSettled(startIndex) {
        const forcedFinish = this.iteration > this.iterationLimit;
        for (let i = startIndex; i < this.diceList.length; i++) {
            if (this.resolveDie(this.diceList[i], forcedFinish) !== 'settled')
                return false;
        }
        return true;
    }
    async remove(diceIdArray) {
        return new Promise(resolve => {
            const results = [];
            for (const dieId of diceIdArray) {
                const mesh = this.diceList[dieId];
                if (mesh.body)
                    this.world.removeBody(mesh.body);
                this.scene.remove(mesh);
                mesh.storeRolledValue('remove');
                results.push(this.getDiceResults(dieId));
            }
            this.renderer.render(this.scene, this.camera);
            this.onRemoveDiceComplete(results);
            document.dispatchEvent(new CustomEvent('removeDiceComplete', { detail: results }));
            resolve(results);
        });
    }
}
DiceBox.WALLS_GROUP = 1;
DiceBox.NON_DET_GROUP = 1 << 1;
DiceBox.DEFAULT_REMOVAL = {
    style: 'shrink',
    dwellMs: 1000,
    durationMs: 450,
};
export { DiceBox };
