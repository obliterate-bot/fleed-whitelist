const fs = require('fs');

const code = fs.readFileSync('./goldeneaglehub.ultra.luau', 'utf8');

// Find snippets containing 'Root' or 'HumanoidObject' or 'Direction'
const queries = ['Root', 'HumanoidObject', 'Direction', 'Connect'];
for (const q of queries) {
  let idx = 0;
  console.log(`=== Matches for "${q}" ===`);
  let count = 0;
  while ((idx = code.indexOf(q, idx)) !== -1 && count < 5) {
    const snippet = code.substring(Math.max(0, idx - 40), Math.min(code.length, idx + 40));
    console.log(`[${count+1}] ... ${snippet.replace(/\n/g, ' ')} ...`);
    idx += q.length;
    count++;
  }
}
