import { COLORSETS } from './const/colorsets.js';
import { TEXTURELIST } from './const/texturelist.js';
export class DiceColors {
    constructor(options = {}) {
        this.colorsets = [];
        this.assetPath = options.assetPath;
    }
    async ImageLoader(data) {
        if (Array.isArray(data)) {
            for (let i = 0, l = data.length; i < l; i++) {
                data[i] = await this.ImageLoader(data[i]);
            }
            return data;
        }
        if (data.source && data.source !== '') {
            data.texture = await this.loadImage(data.source);
        }
        if (data.source_bump && data.source_bump !== '') {
            data.bump = await this.loadImage(data.source_bump);
        }
        return data;
    }
    loadImage(src) {
        const url = this.assetPath + src;
        return new Promise((resolve, reject) => {
            const img = new Image();
            img.onload = () => resolve(img);
            img.crossOrigin = 'anonymous';
            img.src = url;
            img.onerror = () => reject(new Error(`Image load failed: ${url}`));
        }).catch(error => {
            console.error(`[dice-engine] Unable to load image texture: ${url}`, error);
        });
    }
    async getColorSet(options) {
        let setName;
        if (typeof options === 'string')
            setName = options;
        if (typeof options === 'object')
            setName = options.colorset;
        if (Object.hasOwn(this.colorsets, setName)) {
            return this.colorsets[setName];
        }
        const colorset = COLORSETS[setName];
        const texture = options.texture || colorset.texture;
        colorset.texture = this.getTexture(texture);
        colorset.texture = await this.ImageLoader(colorset.texture);
        if (options.material)
            colorset.texture.material = options.material;
        this.colorsets[setName] = colorset;
        return colorset;
    }
    async makeColorSet(options = {}) {
        if (Object.hasOwn(this.colorsets, options.name)) {
            return this.colorsets[options.name];
        }
        const defaultSet = COLORSETS['white'];
        const colorset = { ...defaultSet, ...options };
        const texture = this.getTexture(colorset.texture);
        colorset.texture = await this.ImageLoader(texture);
        if (options.material)
            colorset.texture.material = options.material;
        if (colorset.name.toLowerCase() === 'white') {
            // create a unique name
            colorset.name = `${Date.now()}`;
        }
        this.colorsets[colorset.name] = colorset;
        return colorset;
    }
    getTexture(texturename) {
        if (Array.isArray(texturename)) {
            return texturename.map(name => this.getTexture(name));
        }
        if (Object.hasOwn(TEXTURELIST, texturename)) {
            return TEXTURELIST[texturename];
        }
        return TEXTURELIST['none'];
    }
}
