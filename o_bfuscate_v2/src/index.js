// src/index.js
// Main entrypoint for O_bfuscate V2 (High-Performance Luau Obfuscator)

const { ObfuscatorEngine, obfuscate, PRESETS } = require('./engine');
const { Parser } = require('./core/parser');
const { Lexer } = require('./core/lexer');
const { Generator } = require('./core/generator');

module.exports = {
  ObfuscatorEngine,
  obfuscate,
  PRESETS,
  Parser,
  Lexer,
  Generator
};
