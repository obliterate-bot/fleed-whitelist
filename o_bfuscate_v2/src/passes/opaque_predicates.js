// src/passes/opaque_predicates.js
// Invariant Mathematical Opaque Predicates & Decoy Dead-Code Injection

const { NodeType, ASTNode, walk } = require('../core/ast');

class OpaquePredicatesPass {
  constructor(options = {}) {
    this.options = {
      intensity: options.opaqueIntensity !== undefined ? options.opaqueIntensity : 1, // 0 = off, 1 = moderate, 2 = aggressive
      injectDecoys: options.injectDecoys !== false,
      ...options
    };
  }

  apply(ast) {
    if (this.options.intensity <= 0) return ast;

    const candidateBlocks = [];

    walk(ast, {
      enter: (node) => {
        if (node.type === NodeType.Chunk || node.type === NodeType.DoStatement) {
          if (node.body && node.body.length >= 1) {
            candidateBlocks.push(node.body);
          }
        }
      }
    });

    for (const body of candidateBlocks) {
      if (Math.random() < 0.6) {
        const insertIdx = Math.floor(Math.random() * body.length);
        const opaqueStmt = this.generateOpaquePredicateStatement(body[insertIdx]);
        if (opaqueStmt) {
          body[insertIdx] = opaqueStmt;
        }
      }
    }

    return ast;
  }

  generateAlwaysTruePredicate() {
    const type = Math.floor(Math.random() * 3);

    switch (type) {
      case 0: {
        // (12345 * 12345 >= 0)
        const n = Math.floor(Math.random() * 500) + 10;
        return new ASTNode(NodeType.BinaryExpression, {
          operator: '>=',
          left: new ASTNode(NodeType.BinaryExpression, {
            operator: '*',
            left: new ASTNode(NodeType.NumericLiteral, { value: n, raw: String(n) }),
            right: new ASTNode(NodeType.NumericLiteral, { value: n, raw: String(n) })
          }),
          right: new ASTNode(NodeType.NumericLiteral, { value: 0, raw: '0' })
        });
      }

      case 1: {
        // ((n * n + n) % 2 == 0) -> n^2 + n is always even for any integer n
        const n = Math.floor(Math.random() * 50) + 2;
        return new ASTNode(NodeType.BinaryExpression, {
          operator: '==',
          left: new ASTNode(NodeType.BinaryExpression, {
            operator: '%',
            left: new ASTNode(NodeType.BinaryExpression, {
              operator: '+',
              left: new ASTNode(NodeType.BinaryExpression, {
                operator: '*',
                left: new ASTNode(NodeType.NumericLiteral, { value: n, raw: String(n) }),
                right: new ASTNode(NodeType.NumericLiteral, { value: n, raw: String(n) })
              }),
              right: new ASTNode(NodeType.NumericLiteral, { value: n, raw: String(n) })
            }),
            right: new ASTNode(NodeType.NumericLiteral, { value: 2, raw: '2' })
          }),
          right: new ASTNode(NodeType.NumericLiteral, { value: 0, raw: '0' })
        });
      }

      case 2:
      default: {
        // ((n * 2) % 2 == 0)
        const n = Math.floor(Math.random() * 200) + 1;
        return new ASTNode(NodeType.BinaryExpression, {
          operator: '==',
          left: new ASTNode(NodeType.BinaryExpression, {
            operator: '%',
            left: new ASTNode(NodeType.BinaryExpression, {
              operator: '*',
              left: new ASTNode(NodeType.NumericLiteral, { value: n, raw: String(n) }),
              right: new ASTNode(NodeType.NumericLiteral, { value: 2, raw: '2' })
            }),
            right: new ASTNode(NodeType.NumericLiteral, { value: 2, raw: '2' })
          }),
          right: new ASTNode(NodeType.NumericLiteral, { value: 0, raw: '0' })
        });
      }
    }
  }

  generateDecoyDeadCode() {
    // Realistic dummy code that never executes
    return [
      new ASTNode(NodeType.LocalStatement, {
        variables: [new ASTNode(NodeType.Identifier, { name: '_decoy_' + Math.floor(Math.random() * 1000) })],
        init: [
          new ASTNode(NodeType.BinaryExpression, {
            operator: '+',
            left: new ASTNode(NodeType.NumericLiteral, { value: 0xDEAD, raw: '0xDEAD' }),
            right: new ASTNode(NodeType.NumericLiteral, { value: 0xBEEF, raw: '0xBEEF' })
          })
        ]
      })
    ];
  }

  generateOpaquePredicateStatement(realStatement) {
    if (!realStatement) return null;
    if (
      realStatement.type === NodeType.LocalStatement ||
      realStatement.type === NodeType.LocalFunctionDeclaration ||
      realStatement.type === NodeType.ReturnStatement ||
      realStatement.type === NodeType.BreakStatement ||
      realStatement.type === NodeType.ContinueStatement
    ) {
      return null;
    }

    const condition = this.generateAlwaysTruePredicate();
    const decoyBody = this.generateDecoyDeadCode();

    return new ASTNode(NodeType.IfStatement, {
      clauses: [{
        condition,
        body: [realStatement]
      }],
      elseBody: this.options.injectDecoys ? decoyBody : null
    });
  }
}

module.exports = {
  OpaquePredicatesPass
};
