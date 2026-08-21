const fs = require('fs');
const { Parser } = require('../src/core/parser');
const { ScopeAnalyzer } = require('../src/core/scope');
const { NodeType, walk } = require('../src/core/ast');

const s = fs.readFileSync('./goldeneaglehub.luau', 'utf8');
const p = new Parser(s);
const ast = p.parse();

const analyzer = new ScopeAnalyzer(ast);
const { allScopes } = analyzer.analyze();

for (const name of ['OpenTab', 'TerminalInput', 'CustomGoalPresetPrevious', 'OpenLeaderboardStyle']) {
  let decls = 0;
  let refs = 0;
  for (const sc of allScopes) {
    if (sc.declarations.has(name)) {
      decls++;
      refs += sc.declarations.get(name).references.length;
    }
  }
  let astNodes = 0;
  let globalNodes = 0;
  walk(ast, {
    enter: (node) => {
      if (node.type === NodeType.Identifier && node.name === name) {
        astNodes++;
        if (node.isGlobal) globalNodes++;
      }
    }
  });
  console.log(`[${name}] decls: ${decls}, refs: ${refs}, astNodes: ${astNodes}, globalNodes: ${globalNodes}`);
}
