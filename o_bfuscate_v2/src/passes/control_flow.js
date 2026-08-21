const { NodeType, ASTNode, walk, cloneNode } = require('../core/ast');

class ControlFlowFlatteningPass {
  constructor(options = {}) {
    this.options = {
      intensity: options.cffIntensity !== undefined ? options.cffIntensity : 1, // 0 = off, 1 = function level, 2 = deep
      maxBlocksPerFunction: options.maxCffBlocks || 12,
      ...options
    };
    this.flattenCount = 0;
  }

  apply(ast) {
    if (this.options.intensity <= 0) return ast;

    const maxTargets = this.options.maxFlattenCount || (this.options.intensity > 1 ? 80 : 30);
    const targets = [];

    // Find candidate function bodies
    walk(ast, {
      enter: (node) => {
        if (targets.length >= maxTargets) return;
        if (
          node.type === NodeType.FunctionDeclaration ||
          node.type === NodeType.LocalFunctionDeclaration ||
          node.type === NodeType.FunctionExpression
        ) {
          if (node.body && node.body.length >= 2 && node.body.length <= 40) {
            targets.push(node);
          }
        }
      }
    });

    for (const target of targets) {
      if (this.flattenCount >= maxTargets) break;
      target.body = this.flattenBlock(target.body);
      this.flattenCount++;
    }

    return ast;
  }

  flattenBlock(statements) {
    if (!statements || statements.length < 2) return statements;

    // Split statements into basic blocks
    const blocks = [];
    let currentBlock = [];

    for (const stmt of statements) {
      currentBlock.push(stmt);
      // Split on major control statements or every 2-3 statements
      if (
        stmt.type === NodeType.IfStatement ||
        stmt.type === NodeType.WhileStatement ||
        stmt.type === NodeType.ForNumericStatement ||
        stmt.type === NodeType.ForGenericStatement ||
        stmt.type === NodeType.CallStatement ||
        stmt.type === NodeType.AssignmentStatement ||
        currentBlock.length >= 2
      ) {
        blocks.push(currentBlock);
        currentBlock = [];
      }
    }
    if (currentBlock.length > 0) {
      blocks.push(currentBlock);
    }

    if (blocks.length < 2) return statements;

    // Collect and hoist all LocalStatement variables so they are visible across all state blocks
    const hoistedVars = [];
    const hoistedVarNames = new Set();

    for (let i = 0; i < blocks.length; i++) {
      const newBlock = [];
      for (const stmt of blocks[i]) {
        if (stmt.type === NodeType.LocalStatement) {
          for (const v of stmt.variables) {
            if (!hoistedVarNames.has(v.name)) {
              hoistedVarNames.add(v.name);
              hoistedVars.push(new ASTNode(NodeType.Identifier, { name: v.name }));
            }
          }
          if (stmt.init && stmt.init.length > 0) {
            // Convert local a, b = 1, 2 to a, b = 1, 2
            newBlock.push(new ASTNode(NodeType.AssignmentStatement, {
              variables: stmt.variables.map(v => cloneNode(v)),
              init: stmt.init
            }));
          }
        } else if (stmt.type === NodeType.LocalFunctionDeclaration) {
          if (!hoistedVarNames.has(stmt.identifier.name)) {
            hoistedVarNames.add(stmt.identifier.name);
            hoistedVars.push(new ASTNode(NodeType.Identifier, { name: stmt.identifier.name }));
          }
          newBlock.push(new ASTNode(NodeType.AssignmentStatement, {
            variables: [new ASTNode(NodeType.Identifier, { name: stmt.identifier.name })],
            init: [new ASTNode(NodeType.FunctionExpression, {
              parameters: stmt.parameters,
              isVararg: stmt.isVararg,
              body: stmt.body
            })]
          }));
        } else {
          newBlock.push(stmt);
        }
      }
      blocks[i] = newBlock;
    }

    // Generate unique random state IDs for each block
    const stateIds = [];
    const usedIds = new Set();

    for (let i = 0; i <= blocks.length; i++) {
      let id;
      do {
        id = Math.floor(Math.random() * 900) + 100;
      } while (usedIds.has(id));
      usedIds.add(id);
      stateIds.push(id);
    }

    const initialState = stateIds[0];
    const exitState = stateIds[blocks.length];

    // State variable name
    const stateVar = `_cff_st_${Math.floor(Math.random() * 1000)}`;

    // Build dispatcher if-elseif chain
    const clauses = [];

    for (let i = 0; i < blocks.length; i++) {
      const curState = stateIds[i];
      const nextState = stateIds[i + 1];
      const blockStmts = [...blocks[i]];

      // Check if last statement is a return or break
      const lastStmt = blockStmts[blockStmts.length - 1];
      const isTerminating = lastStmt && (lastStmt.type === NodeType.ReturnStatement || lastStmt.type === NodeType.BreakStatement);

      if (!isTerminating) {
        // Transition to next state
        blockStmts.push(new ASTNode(NodeType.AssignmentStatement, {
          variables: [new ASTNode(NodeType.Identifier, { name: stateVar })],
          init: [new ASTNode(NodeType.NumericLiteral, { value: nextState, raw: `0x${nextState.toString(16)}` })]
        }));
      }

      clauses.push({
        condition: new ASTNode(NodeType.BinaryExpression, {
          operator: '==',
          left: new ASTNode(NodeType.Identifier, { name: stateVar }),
          right: new ASTNode(NodeType.NumericLiteral, { value: curState, raw: `0x${curState.toString(16)}` })
        }),
        body: blockStmts
      });
    }

    // Add 1-2 bogus unreachable states to confuse decompilers
    for (let k = 0; k < 2; k++) {
      let fakeId;
      do {
        fakeId = Math.floor(Math.random() * 900) + 100;
      } while (usedIds.has(fakeId));
      usedIds.add(fakeId);

      clauses.push({
        condition: new ASTNode(NodeType.BinaryExpression, {
          operator: '==',
          left: new ASTNode(NodeType.Identifier, { name: stateVar }),
          right: new ASTNode(NodeType.NumericLiteral, { value: fakeId, raw: `0x${fakeId.toString(16)}` })
        }),
        body: [
          new ASTNode(NodeType.AssignmentStatement, {
            variables: [new ASTNode(NodeType.Identifier, { name: stateVar })],
            init: [new ASTNode(NodeType.NumericLiteral, { value: exitState, raw: `0x${exitState.toString(16)}` })]
          })
        ]
      });
    }

    // Shuffle clauses non-linearly
    for (let i = clauses.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1));
      [clauses[i], clauses[j]] = [clauses[j], clauses[i]];
    }

    const whileLoop = new ASTNode(NodeType.WhileStatement, {
      condition: new ASTNode(NodeType.BinaryExpression, {
        operator: '~=',
        left: new ASTNode(NodeType.Identifier, { name: stateVar }),
        right: new ASTNode(NodeType.NumericLiteral, { value: exitState, raw: `0x${exitState.toString(16)}` })
      }),
      body: [
        new ASTNode(NodeType.IfStatement, {
          clauses,
          elseBody: [new ASTNode(NodeType.BreakStatement)]
        })
      ]
    });

    const resultBody = [];
    if (hoistedVars.length > 0) {
      resultBody.push(new ASTNode(NodeType.LocalStatement, {
        variables: hoistedVars,
        init: []
      }));
    }
    resultBody.push(new ASTNode(NodeType.LocalStatement, {
      variables: [new ASTNode(NodeType.Identifier, { name: stateVar })],
      init: [new ASTNode(NodeType.NumericLiteral, { value: initialState, raw: `0x${initialState.toString(16)}` })]
    }));
    resultBody.push(whileLoop);

    return resultBody;
  }
}

module.exports = {
  ControlFlowFlatteningPass
};
