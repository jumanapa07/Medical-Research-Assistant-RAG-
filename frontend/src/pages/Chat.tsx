
import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type KeyboardEvent,
} from "react";
import { useNavigate } from "react-router-dom";
import { chatService } from "../services/chatService";
import type { Conversation, Message } from "../types/chat";
import axios from "axios";
import AppHeader from "../components/AppHeader";

import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";

// Markdown formatting for assistant responses
const markdownComponents: Components = {
  h1: ({ children }) => (
    <h1 className="mb-4 mt-6 text-2xl font-bold text-slate-900">
      {children}
    </h1>
  ),

  h2: ({ children }) => (
    <h2 className="mb-3 mt-6 text-xl font-semibold text-slate-900">
      {children}
    </h2>
  ),

  h3: ({ children }) => (
    <h3 className="mb-2 mt-5 text-lg font-semibold text-slate-900">
      {children}
    </h3>
  ),

  p: ({ children }) => (
    <p className="mb-4 text-sm leading-7 text-slate-700 last:mb-0">
      {children}
    </p>
  ),

  strong: ({ children }) => (
    <strong className="font-semibold text-slate-900">
      {children}
    </strong>
  ),

  em: ({ children }) => (
    <em className="italic">{children}</em>
  ),

  ul: ({ children }) => (
    <ul className="mb-4 ml-6 list-disc space-y-2 text-sm leading-7 text-slate-700">
      {children}
    </ul>
  ),

  ol: ({ children }) => (
    <ol className="mb-4 ml-6 list-decimal space-y-2 text-sm leading-7 text-slate-700">
      {children}
    </ol>
  ),

  li: ({ children }) => (
    <li className="pl-1">{children}</li>
  ),

  blockquote: ({ children }) => (
    <blockquote className="my-4 border-l-4 border-teal-500 pl-4 text-sm leading-7 text-slate-600">
      {children}
    </blockquote>
  ),

  table: ({ children }) => (
    <div className="my-5 w-full overflow-x-auto rounded-lg border border-slate-200">
      <table className="w-full min-w-[500px] border-collapse text-left text-sm">
        {children}
      </table>
    </div>
  ),

  thead: ({ children }) => (
    <thead className="bg-slate-100 text-slate-800">
      {children}
    </thead>
  ),

  th: ({ children }) => (
    <th className="border-b border-slate-200 px-4 py-3 font-semibold">
      {children}
    </th>
  ),

  td: ({ children }) => (
    <td className="border-b border-slate-100 px-4 py-3 align-top text-slate-700">
      {children}
    </td>
  ),

  code: ({ children, className }) => {
    const isCodeBlock = Boolean(className?.includes("language-"));

    return (
      <code
        className={
          isCodeBlock
            ? "font-mono text-sm text-slate-100"
            : "rounded bg-slate-100 px-1.5 py-0.5 font-mono text-[0.85em] text-teal-800"
        }
      >
        {children}
      </code>
    );
  },

  pre: ({ children }) => (
    <pre className="my-4 overflow-x-auto rounded-lg bg-slate-900 p-4 text-sm leading-6 text-slate-100">
      {children}
    </pre>
  ),

  a: ({ children, href }) => (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="text-teal-700 underline underline-offset-2 hover:text-teal-900"
    >
      {children}
    </a>
  ),

  hr: () => <hr className="my-5 border-slate-200" />,
};

export default function Chat() {
  const navigate = useNavigate();
  const bottomRef = useRef<HTMLDivElement>(null);

  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeConversation, setActiveConversation] =
    useState<Conversation | null>(null);

  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState("");

  // Load conversations
  const loadConversations = useCallback(async () => {
    try {
      const data = await chatService.getConversations();
      setConversations(data);
    } catch {
      setError("Unable to load conversations.");
    } finally {
      setLoading(false);
    }
  }, []);

  // Load messages for selected conversation
  const loadMessages = useCallback(async (conversationId: string) => {
    try {
      const data = await chatService.getMessages(conversationId);
      setMessages(data);
    } catch {
      setError("Unable to load conversation messages.");
    }
  }, []);

  useEffect(() => {
    loadConversations();
  }, [loadConversations]);

  useEffect(() => {
    if (activeConversation) {
      setMessages([]);
      loadMessages(activeConversation.id);
    } else {
      setMessages([]);
    }
  }, [activeConversation, loadMessages]);

  // Scroll to latest message
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, sending]);

  // Create a new conversation
  const handleNewConversation = async () => {
    setError("");

    try {
      const conversation = await chatService.createConversation({
        title: "New research conversation",
      });

      setConversations((previous) => [conversation, ...previous]);
      setActiveConversation(conversation);
      setMessages([]);
    } catch {
      setError("Unable to create a conversation.");
    }
  };

  // Send a message
  const handleSend = async () => {
    const question = input.trim();

    if (!question || !activeConversation || sending) return;

    setSending(true);
    setError("");
    setInput("");

    const temporaryMessage: Message = {
      id: `temporary-${Date.now()}`,
      conversation_id: activeConversation.id,
      role: "user",
      content: question,
      citations: [],
      created_at: new Date().toISOString(),
    };

    setMessages((previous) => [...previous, temporaryMessage]);

    try {
      const response = await chatService.sendMessage(
        activeConversation.id,
        {
          question: question,
        }
      );

      const assistantMessage: Message = {
        id: `response-${Date.now()}`,
        conversation_id: activeConversation.id,
        role: "assistant",
        content: response.answer,
        citations: response.citations ?? [],
        created_at: new Date().toISOString(),
      };

      setMessages((previous) => [
        ...previous,
        assistantMessage,
      ]);

      await loadConversations();
    } catch (err) {
      setMessages((previous) =>
        previous.filter(
          (message) => message.id !== temporaryMessage.id
        )
      );

      if (axios.isAxiosError(err)) {
        setError(
          err.response?.data?.detail ||
            "Unable to send your question."
        );
      } else {
        setError("Unable to send your question.");
      }

      setInput(question);
    } finally {
      setSending(false);
    }
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div className="min-h-screen bg-white">
      <AppHeader />

      <div className="mx-auto flex h-[calc(100vh-3.5rem)] max-w-6xl overflow-hidden border-x border-slate-200">

        {/* Sidebar */}
        <aside className="hidden w-72 shrink-0 flex-col border-r border-slate-200 bg-slate-50 md:flex">

          <div className="p-4">
            <button
              onClick={handleNewConversation}
              className="flex w-full items-center justify-center gap-2 rounded-lg bg-teal-700 px-4 py-2.5 text-sm font-medium text-white transition hover:bg-teal-800"
            >
              <svg
                viewBox="0 0 24 24"
                className="h-4 w-4"
                fill="none"
                stroke="currentColor"
                strokeWidth="2.2"
                strokeLinecap="round"
              >
                <path d="M12 5v14M5 12h14" />
              </svg>
              New conversation
            </button>
          </div>

          <div className="flex-1 overflow-y-auto px-3 pb-3">
            <p className="px-2 pb-2 text-xs font-medium text-slate-500">
              Recent
            </p>

            {loading ? (
              <p className="px-2 text-sm text-slate-500">
                Loading...
              </p>
            ) : conversations.length === 0 ? (
              <p className="px-2 text-sm text-slate-500">
                No conversations yet.
              </p>
            ) : (
              <ul className="space-y-0.5">
                {conversations.map((conversation) => {
                  const active =
                    activeConversation?.id === conversation.id;

                  return (
                    <li key={conversation.id}>
                      <button
                        onClick={() =>
                          setActiveConversation(conversation)
                        }
                        className={`w-full rounded-lg px-3 py-2 text-left text-sm transition ${
                          active
                            ? "bg-white font-medium text-slate-900 shadow-sm ring-1 ring-slate-200"
                            : "text-slate-600 hover:bg-slate-100"
                        }`}
                      >
                        <span className="block truncate">
                          {conversation.title ||
                            "Untitled conversation"}
                        </span>
                      </button>
                    </li>
                  );
                })}
              </ul>
            )}
          </div>

          <div className="border-t border-slate-200 p-3">
            <button
              onClick={() => navigate("/documents")}
              className="w-full rounded-lg px-3 py-2 text-left text-sm text-slate-600 transition hover:bg-slate-100 hover:text-slate-900"
            >
              Manage documents
            </button>
          </div>
        </aside>

        {/* Main chat */}
        <main className="flex min-w-0 flex-1 flex-col">

          {/* Chat header */}
          <div className="border-b border-slate-200 px-6 py-3">
            <h1 className="truncate text-sm font-semibold text-slate-900">
              {activeConversation?.title || "Research assistant"}
            </h1>

            <p className="text-xs text-slate-500">
              Answers are grounded in your uploaded documents.
            </p>
          </div>

          {/* Messages */}
          <section className="flex-1 overflow-y-auto px-4 py-8 sm:px-8">
            <div className="mx-auto flex w-full max-w-4xl flex-col gap-8">

              {!activeConversation && (
                <div className="py-20 text-center">
                  <h2 className="text-lg font-semibold text-slate-900">
                    Ask your research papers
                  </h2>

                  <p className="mx-auto mt-2 max-w-sm text-sm leading-6 text-slate-500">
                    Start a conversation to ask questions about your uploaded
                    medical literature.
                  </p>

                  <button
                    onClick={handleNewConversation}
                    className="mt-6 rounded-lg bg-teal-700 px-5 py-2.5 text-sm font-medium text-white transition hover:bg-teal-800"
                  >
                    Start a conversation
                  </button>
                </div>
              )}

              {activeConversation && messages.length === 0 && (
                <div className="py-20 text-center text-sm text-slate-500">
                  Ask a question about your uploaded papers.
                </div>
              )}

              {messages.map((message) =>
                message.role === "user" ? (

                  /* User message */
                  <div
                    key={message.id}
                    className="flex justify-end"
                  >
                    <div className="max-w-[80%] rounded-2xl rounded-br-md bg-teal-800 px-5 py-3 text-sm leading-7 text-white shadow-sm">
                      <p className="whitespace-pre-wrap">
                        {message.content}
                      </p>
                    </div>
                  </div>

                ) : (

                  /* Assistant message */
                  <div
                    key={message.id}
                    className="w-full max-w-3xl"
                  >
                    <div className="mb-3 flex items-center gap-2">
                      <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-teal-700 text-xs font-semibold text-white">
                        AI
                      </div>

                      <span className="text-sm font-medium text-slate-700">
                        Research Assistant
                      </span>
                    </div>

                    {/* Markdown response */}
                    <article className="break-words text-sm leading-7 text-slate-700">
                      <ReactMarkdown
                        remarkPlugins={[remarkGfm]}
                        components={markdownComponents}
                      >
                        {message.content}
                      </ReactMarkdown>
                    </article>

                    {/* Simple source references */}
                    {message.citations?.length > 0 && (
                      <div className="mt-4 border-t border-slate-100 pt-3">
                        <p className="mb-2 text-xs font-semibold text-slate-500">
                          Sources
                        </p>

                        <div className="flex flex-wrap gap-x-5 gap-y-2">
                          {message.citations.map((citation) => (
                            <span
                              key={`${message.id}-${citation.source_number}`}
                              className="text-xs text-teal-700"
                            >
                              [Source {citation.source_number}]{" "}
                              {citation.title}
                              {citation.page_start != null &&
                                ` · Page ${citation.page_start}${
                                  citation.page_end != null &&
                                  citation.page_end !== citation.page_start
                                    ? `–${citation.page_end}`
                                    : ""
                                }`}
                            </span>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                )
              )}

              {/* Loading indicator */}
              {sending && (
                <div
                  className="flex items-center gap-3 text-sm text-slate-500"
                  aria-live="polite"
                >
                  <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-teal-700 text-xs font-bold text-white">
                    AI
                  </div>

                  <span className="flex items-center gap-2">
                    <span className="flex gap-1">
                      <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-teal-600" />
                      <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-teal-600 [animation-delay:150ms]" />
                      <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-teal-600 [animation-delay:300ms]" />
                    </span>

                    Researching your question...
                  </span>
                </div>
              )}

              <div ref={bottomRef} />
            </div>
          </section>

          {/* Composer */}
          <footer className="border-t border-slate-200 bg-white px-4 py-4 sm:px-8">
            <div className="mx-auto max-w-3xl">

              {error && (
                <p
                  role="alert"
                  className="mb-3 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700"
                >
                  {error}
                </p>
              )}

              <div className="flex items-end gap-2 rounded-xl border border-slate-300 bg-white p-2 transition focus-within:border-teal-600 focus-within:ring-2 focus-within:ring-teal-600/20">
                <textarea
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={handleKeyDown}
                  disabled={!activeConversation || sending}
                  rows={1}
                  placeholder={
                    activeConversation
                      ? "Ask a question about your research..."
                      : "Start a new conversation first"
                  }
                  className="max-h-40 min-h-10 flex-1 resize-none border-0 bg-transparent px-2 py-2 text-sm text-slate-900 outline-none placeholder:text-slate-400 disabled:cursor-not-allowed"
                />

                <button
                  onClick={handleSend}
                  disabled={
                    !input.trim() || !activeConversation || sending
                  }
                  className="rounded-lg bg-teal-700 px-4 py-2 text-sm font-medium text-white transition hover:bg-teal-800 disabled:cursor-not-allowed disabled:opacity-40"
                >
                  Send
                </button>
              </div>

              <p className="mt-2 text-center text-xs text-slate-400">
                Verify answers against the cited sources before relying on them.
              </p>
            </div>
          </footer>
        </main>
      </div>
    </div>
  );
}
