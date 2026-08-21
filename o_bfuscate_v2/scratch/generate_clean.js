const fs = require('fs');
const { Parser } = require('../src/core/parser');
const { ObfuscatorEngine } = require('../src/engine');
const { Generator } = require('../src/core/generator');

const s = fs.readFileSync('./goldeneaglehub.luau', 'utf8');
const engine = new ObfuscatorEngine({ preset: 'ultra-secure' });
const res = engine.obfuscate(s);

console.log('Result length:', res.code.length);
console.log('Includes OpenTab:', res.code.includes('OpenTab'));
console.log('Includes IsTorsoPart:', res.code.includes('IsTorsoPart'));
console.log('Includes TerminalStroke:', res.code.includes('TerminalStroke'));
fs.writeFileSync('./goldeneaglehub.ultra.luau', res.code, 'utf8');
