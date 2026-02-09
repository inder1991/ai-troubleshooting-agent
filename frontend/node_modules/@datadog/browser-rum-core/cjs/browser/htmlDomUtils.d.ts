export declare function isTextNode(node: Node): node is Text;
export declare function isCommentNode(node: Node): node is Comment;
export declare function isElementNode(node: Node): node is Element;
export declare function isNodeShadowHost(node: Node): node is Element & {
    shadowRoot: ShadowRoot;
};
export declare function isNodeShadowRoot(node: Node): node is ShadowRoot;
export declare function hasChildNodes(node: Node): boolean;
export declare function forEachChildNodes(node: Node, callback: (child: Node) => void): void;
/**
 * Return `host` in case if the current node is a shadow root otherwise will return the `parentNode`
 */
export declare function getParentNode(node: Node): Node | null;
