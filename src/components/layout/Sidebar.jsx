export default function Sidebar() {
  return (
    <aside className="w-64 bg-[var(--color-surface)] p-4 h-full">
      <div className="mb-4">
        <h2 className="text-[var(--color-text-primary)] text-xl font-bold">Chat History</h2>
      </div>
      <nav>
        <ul className="space-y-2">
          <li>
            <button className="w-full text-left p-2 rounded hover:bg-[var(--color-hover)] text-[var(--color-text-secondary)]">
              New Chat
            </button>
          </li>
          {/* Add chat history items here */}
        </ul>
      </nav>
    </aside>
  );
}