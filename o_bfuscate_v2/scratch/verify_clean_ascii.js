const fs = require('fs');
const { obfuscate } = require('../src/engine');

const s = fs.readFileSync('./goldeneaglehub.luau', 'utf8');

console.log('Obfuscating with ultra-secure preset...');
const res = obfuscate(s, { preset: 'ultra-secure' });

fs.writeFileSync('./goldeneaglehub.ultra.luau', res.code, 'utf8');
console.log('Saved goldeneaglehub.ultra.luau, size:', res.code.length);

// Extract all ASCII/Latin-only words of length >= 3
const asciiWords = res.code.match(/[a-zA-Z]{3,}/g) || [];
const wordCounts = new Map();
for (const w of asciiWords) {
  wordCounts.set(w, (wordCounts.get(w) || 0) + 1);
}

// Filter out standard Lua keywords and runtime words
const ALLOWED_RUNTIME_WORDS = new Set([
  'local', 'function', 'return', 'then', 'else', 'elseif', 'while', 'repeat', 'until', 'break', 'continue',
  'true', 'false', 'nil', 'self', 'pcall', 'type', 'math', 'string', 'table', 'bit32', 'bxor', 'buffer',
  'getfenv', 'native', 'optimize', 'protected', 'O_bfuscate', 'created', 'Undix', 'create', 'writeu8', 'readstring',
  'char', 'concat', 'error', 'pairs', 'ipairs', 'select', 'unpack', 'tostring', 'tonumber', 'setmetatable', 'getrawmetatable'
]);

const suspiciousWords = [];
for (const [w, count] of wordCounts.entries()) {
  if (!ALLOWED_RUNTIME_WORDS.has(w)) {
    suspiciousWords.push({ word: w, count });
  }
}

console.log('Total suspicious ASCII words found:', suspiciousWords.length);
if (suspiciousWords.length > 0) {
  console.log('Suspicious words:');
  for (const item of suspiciousWords) {
    console.log(`  "${item.word}": ${item.count} times`);
  }
} else {
  console.log('🎉 PERFECT! ZERO plain source words, zero plain strings, zero residual identifiers!');
}
