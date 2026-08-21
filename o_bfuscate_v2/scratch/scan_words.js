const fs = require('fs');

const code = fs.readFileSync('./goldeneaglehub.ultra.luau', 'utf8');

// Find all words / identifiers of length >= 4
const identRegex = /[a-zA-Z_][a-zA-Z0-9_]*/g;
const words = new Map();
let m;
while ((m = identRegex.exec(code)) !== null) {
  const w = m[0];
  if (w.length >= 4 && !w.startsWith('_0x') && !w.startsWith('_а') && !w.startsWith('_е') && !w.startsWith('_о') && !w.startsWith('_р') && !w.startsWith('_с')) {
    words.set(w, (words.get(w) || 0) + 1);
  }
}

console.log('Total distinct readable words:', words.size);
const sorted = Array.from(words.entries()).sort((a, b) => b[1] - a[1]);
console.log('Top 40 most frequent readable identifiers/words:');
for (let i = 0; i < Math.min(40, sorted.length); i++) {
  console.log(`  ${sorted[i][0]}: ${sorted[i][1]} times`);
}
