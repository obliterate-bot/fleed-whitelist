const fs = require('fs');
const { Parser } = require('../src/core/parser');
const { MemberIndirectionPass } = require('../src/passes/member_indirection');
const { AntiTamperPass } = require('../src/passes/anti_tamper');
const { ControlFlowFlatteningPass } = require('../src/passes/control_flow');
const { OpaquePredicatesPass } = require('../src/passes/opaque_predicates');
const { MBAPass } = require('../src/passes/mba_constants');
const { StringCryptoPass } = require('../src/passes/string_crypto');
const { IdentifierMangler } = require('../src/passes/mangler');
const { walk, NodeType } = require('../src/core/ast');

const s = fs.readFileSync('./goldeneaglehub.luau', 'utf8');
const p = new Parser(s);
const ast = p.parse();

new MemberIndirectionPass().apply(ast);
new AntiTamperPass().apply(ast);
new ControlFlowFlatteningPass({ cffIntensity: 2 }).apply(ast);
new OpaquePredicatesPass({ opaqueIntensity: 2 }).apply(ast);
new MBAPass({ mbaIntensity: 2 }).apply(ast);
new StringCryptoPass().apply(ast);
new IdentifierMangler({ manglerMode: 'confusables' }).apply(ast);

walk(ast, {
  enter: (node) => {
    if (node.type === NodeType.Identifier && (node.name === 'TerminalInput' || node.name === 'CloseMenus' || node.name === 'CreateLeaderboardColorPicker')) {
      console.log(`[${node.name}] mangledName: ${node.mangledName}, isGlobal: ${node.isGlobal}`);
    }
  }
});
