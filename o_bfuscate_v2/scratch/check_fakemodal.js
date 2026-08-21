const fs = require('fs');
const { Parser } = require('../src/core/parser');
const { ScopeAnalyzer } = require('../src/core/scope');
const { NodeType, walk } = require('../src/core/ast');

const s = fs.readFileSync('./goldeneaglehub.luau', 'utf8');
const p = new Parser(s);
const ast = p.parse();

const analyzer = new ScopeAnalyzer(ast);
const { rootScope, allScopes } = analyzer.analyze();

let declCount = 0;
let refCount = 0;
let globalRef = 0;

for (const sc of allScopes) {
  if (sc.declarations.has('FakeModal')) {
    declCount++;
    const sym = sc.declarations.get('FakeModal');
    console.log('FakeModal declaration found in scope, refs count:', sym.references.length);
  }
}

walk(ast, {
  enter: (node) => {
    if (node.type === NodeType.Identifier && node.name === 'FakeModal') {
      refCount++;
      if (node.isGlobal) globalRef++;
    }
  }
});

console.log('Total FakeModal nodes in AST:', refCount, 'isGlobal:', globalRef);
