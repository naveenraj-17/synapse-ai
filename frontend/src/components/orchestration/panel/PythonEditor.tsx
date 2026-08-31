'use client';

/**
 * Syntax-highlighted Python editor (CodeMirror) for the transform step.
 *
 * Deliberately keeps the one-dark palette in both themes: a code editor is a
 * document, not chrome, and a dark editor inside a light app is a familiar
 * shape (every embedded playground does it) while a half-inverted CodeMirror
 * theme is not.
 */

import { useEffect, useRef } from 'react';
import { EditorView } from '@codemirror/view';
import { basicSetup } from 'codemirror';
import { python } from '@codemirror/lang-python';
import { oneDarkTheme } from '@codemirror/theme-one-dark';
import { EditorState } from '@codemirror/state';
import { HighlightStyle, syntaxHighlighting } from '@codemirror/language';
import { tags } from '@lezer/highlight';

const pythonHighlight = syntaxHighlighting(HighlightStyle.define([
    { tag: tags.keyword, color: '#c792ea', fontWeight: 'bold' },
    { tag: tags.definitionKeyword, color: '#c792ea', fontWeight: 'bold' },
    { tag: tags.self, color: '#f78c6c', fontStyle: 'italic' },
    { tag: tags.bool, color: '#ff9cac' },
    { tag: tags.null, color: '#ff9cac' },
    { tag: tags.definition(tags.function(tags.variableName)), color: '#82aaff', fontWeight: 'bold' },
    { tag: tags.function(tags.variableName), color: '#82aaff' },
    { tag: tags.definition(tags.className), color: '#ffcb6b', fontWeight: 'bold' },
    { tag: tags.className, color: '#ffcb6b' },
    { tag: tags.meta, color: '#ffa759', fontStyle: 'italic' },
    { tag: tags.variableName, color: '#eeffff' },
    { tag: tags.propertyName, color: '#89ddff' },
    { tag: tags.string, color: '#c3e88d' },
    { tag: tags.special(tags.string), color: '#c3e88d' },
    { tag: tags.number, color: '#f78c6c' },
    { tag: tags.operator, color: '#89ddff' },
    { tag: tags.punctuation, color: '#89ddff' },
    { tag: tags.bracket, color: '#ffcb6b' },
    { tag: tags.comment, color: '#546e7a', fontStyle: 'italic' },
    { tag: tags.typeName, color: '#ffcb6b' },
    { tag: tags.escape, color: '#f78c6c' },
]));

export function PythonEditor({ value, onChange }: { value: string; onChange: (code: string) => void }) {
    const containerRef = useRef<HTMLDivElement>(null);
    const editorRef = useRef<EditorView | null>(null);
    const onChangeRef = useRef(onChange);
    onChangeRef.current = onChange;

    useEffect(() => {
        if (!containerRef.current || editorRef.current) return;
        const state = EditorState.create({
            doc: value,
            extensions: [
                basicSetup,
                python(),
                oneDarkTheme,
                pythonHighlight,
                EditorView.updateListener.of((update) => {
                    if (update.docChanged) onChangeRef.current(update.state.doc.toString());
                }),
                EditorView.theme({
                    '&': { backgroundColor: '#09090b', height: '100%' },
                    '.cm-scroller': { overflow: 'auto', fontFamily: 'var(--code-font, monospace)', fontSize: '12px' },
                    '.cm-content': { padding: '8px 0' },
                    '.cm-line': { padding: '0 12px' },
                    '&.cm-focused .cm-cursor': { borderLeftColor: '#d97706' },
                    '.cm-selectionBackground': { backgroundColor: '#3f3f46' },
                    '&.cm-focused .cm-selectionBackground': { backgroundColor: '#78350f' },
                }),
            ],
        });
        editorRef.current = new EditorView({ state, parent: containerRef.current });
        return () => { editorRef.current?.destroy(); editorRef.current = null; };
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);

    // Sync external value changes (e.g. step switching)
    useEffect(() => {
        const view = editorRef.current;
        if (!view) return;
        const current = view.state.doc.toString();
        if (current !== value) {
            view.dispatch({ changes: { from: 0, to: current.length, insert: value } });
        }
    }, [value]);

    return <div ref={containerRef} className="h-full" />;
}
