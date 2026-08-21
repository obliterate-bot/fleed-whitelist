const fs = require('fs');

const code = fs.readFileSync('./goldeneaglehub.luau', 'utf8');

const queries = ['FakeModal', 'RefreshOptions', 'TerminalStroke', 'TeleportToPlaceInstance'];
for (const q of queries) {
  const lines = code.split('\n');
  for (let i = 0; i < lines.length; i++) {
    if (lines[i].includes(q)) {
      console.log(`[${q}] Line ${i+1}:`, lines[i].trim());
      break;
    }
  }
}
