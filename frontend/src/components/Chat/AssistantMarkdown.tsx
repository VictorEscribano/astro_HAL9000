import { ReactNode, Children } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

/** Wrap each `[N]` citation marker in a styled superscript so they stand
 *  out from prose.  Operates on string-typed children only — anything that
 *  was already wrapped by a markdown element (e.g. inside a link) is left
 *  alone to avoid double-processing. */
function highlightCitations(node: ReactNode, keyPrefix: string): ReactNode {
  if (typeof node !== "string") return node;
  // Split, keeping the matches.  Capture-group ensures `[1]`, `[12]` etc.
  const parts = node.split(/(\[\d+\])/g);
  if (parts.length === 1) return node;
  return parts.map((p, i) =>
    /^\[\d+\]$/.test(p) ? (
      <sup
        key={`${keyPrefix}-${i}`}
        className="text-accent-red font-bold mx-0.5 text-[0.85em] cursor-default"
        title="Citation — see Fuentes section below"
      >
        {p}
      </sup>
    ) : (
      p
    ),
  );
}

function processChildren(children: ReactNode, keyPrefix: string): ReactNode {
  return Children.map(children, (child, i) =>
    highlightCitations(child, `${keyPrefix}-${i}`),
  );
}

/** Markdown renderer for HAL's assistant messages.  Provides:
 *   - GFM extensions (autolinking URLs, tables, strikethrough)
 *   - Links open in a new tab and use the accent color
 *   - `[N]` citation markers highlighted as small superscript red
 *   - Tight typography that fits HAL's terminal-style chat panel */
export default function AssistantMarkdown({ content }: { content: string }) {
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      components={{
        a: ({ href, children, ...rest }) => (
          <a
            href={href}
            target="_blank"
            rel="noopener noreferrer"
            className="text-accent-red underline decoration-accent-red/40 hover:decoration-accent-red break-all"
            {...rest}
          >
            {children}
          </a>
        ),
        p: ({ children }) => (
          <p className="my-1 leading-relaxed break-words">
            {processChildren(children, "p")}
          </p>
        ),
        li: ({ children }) => (
          <li className="ml-3 my-0.5">{processChildren(children, "li")}</li>
        ),
        ul: ({ children }) => <ul className="list-disc ml-3 my-1 space-y-0.5">{children}</ul>,
        ol: ({ children }) => <ol className="list-decimal ml-4 my-1 space-y-0.5">{children}</ol>,
        strong: ({ children }) => (
          <strong className="text-text font-semibold">{processChildren(children, "s")}</strong>
        ),
        em: ({ children }) => <em className="text-text/90 italic">{children}</em>,
        code: ({ children }) => (
          <code className="bg-white/[0.06] text-accent-red/90 px-1 py-0.5 rounded text-[0.92em]">
            {children}
          </code>
        ),
        h1: ({ children }) => <h1 className="text-[1.1em] font-bold mt-2 mb-1">{children}</h1>,
        h2: ({ children }) => <h2 className="text-[1.05em] font-bold mt-2 mb-1">{children}</h2>,
        h3: ({ children }) => <h3 className="font-bold mt-1.5 mb-0.5">{children}</h3>,
        hr: () => <hr className="my-2 border-white/[0.08]" />,
      }}
    >
      {content}
    </ReactMarkdown>
  );
}
