import { useCallback } from "react";
import CodeMirror from "@uiw/react-codemirror";
import { python } from "@codemirror/lang-python";
import { vscodeDark } from "@uiw/codemirror-theme-vscode";
import { EditorView } from "@codemirror/view";
import { useAppStore } from "../../store";

/** Full-panel code editor that lives as a tab inside ObjectView.  Backed by
 *  CodeMirror 6 with Python syntax + the VSCode dark theme so the look
 *  matches the rest of the FUI.  All state is in the Zustand store so the
 *  editor survives tab switches and external triggers (e.g. the
 *  "OPEN IN EDITOR" button on python_exec tool cards). */
export default function CodeInspector() {
  const editorCode = useAppStore((s) => s.editorCode);
  const editorAttached = useAppStore((s) => s.editorAttached);
  const setEditorCode = useAppStore((s) => s.setEditorCode);
  const setEditorAttached = useAppStore((s) => s.setEditorAttached);

  const onChange = useCallback(
    (value: string) => setEditorCode(value),
    [setEditorCode],
  );

  const onCopy = useCallback(async () => {
    try { await navigator.clipboard.writeText(editorCode); } catch { /* no-op */ }
  }, [editorCode]);

  const onClear = useCallback(() => {
    setEditorCode("");
    setEditorAttached(false);
  }, [setEditorCode, setEditorAttached]);

  const lineCount = editorCode ? editorCode.split("\n").length : 0;
  const charCount = editorCode.length;

  return (
    <div className="flex flex-col h-full bg-bg">
      {/* Toolbar */}
      <div className="flex shrink-0 items-center gap-2 px-2 py-1 border-b border-white/[0.06]">
        <span className="text-[calc(7px*var(--fs))] font-mono text-dim/80 tracking-widest">CODE INSPECTOR</span>
        <span className="text-[calc(8px*var(--fs))] font-mono text-white/30">
          {lineCount}L · {charCount}c
        </span>

        <div className="ml-auto flex items-center gap-1">
          {/* Attach toggle — when ON, the next user message will include the
              editor content as system context for the model. */}
          <button
            onClick={() => setEditorAttached(!editorAttached)}
            title={editorAttached
              ? "Editor content attached to next chat turn — click to detach"
              : "Click to attach this code to the next chat turn"}
            className={`text-[calc(8px*var(--fs))] font-mono border px-2 py-0.5 rounded tracking-widest transition-colors
              ${editorAttached
                ? "text-accent-red border-accent-red/40 bg-accent-red/10"
                : "text-dim border-white/[0.08] hover:text-accent-red hover:border-accent-red/30"
              }`}
          >
            {editorAttached ? "◉ ATTACHED" : "○ ATTACH"}
          </button>

          <button
            onClick={onCopy}
            disabled={!editorCode}
            className="text-[calc(8px*var(--fs))] font-mono text-dim hover:text-text border border-white/[0.08]
                       hover:border-accent-red/30 px-2 py-0.5 rounded tracking-widest transition-colors
                       disabled:opacity-30"
          >
            COPY
          </button>
          <button
            onClick={onClear}
            disabled={!editorCode && !editorAttached}
            className="text-[calc(8px*var(--fs))] font-mono text-dim hover:text-accent-red border border-white/[0.08]
                       hover:border-accent-red/30 px-2 py-0.5 rounded tracking-widest transition-colors
                       disabled:opacity-30"
          >
            CLEAR
          </button>
        </div>
      </div>

      {/* Editor — always rendered, even when empty.  Two ways to populate:
          (1) paste/type your own code directly, (2) click "OPEN IN EDITOR"
          on a python_exec tool card to load HAL's generated code. */}
      <div className="flex-1 min-h-0 overflow-hidden relative">
        <CodeMirror
          value={editorCode}
          height="100%"
          theme={vscodeDark}
          extensions={[python(), EditorView.lineWrapping]}
          onChange={onChange}
          placeholder={"# Pega o escribe código Python aquí.\n# Pulsa ATTACH y mándale un mensaje a HAL para que lo revise.\n# O ejecuta una tool de Python desde el chat y usa OPEN IN EDITOR."}
          basicSetup={{
            lineNumbers: true,
            highlightActiveLine: true,
            foldGutter: true,
            autocompletion: true,
            tabSize: 4,
          }}
          style={{ height: "100%", fontSize: "calc(12px * var(--fs))" }}
        />
      </div>
    </div>
  );
}
