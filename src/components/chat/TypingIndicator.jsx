import Avatar from './Avatar';

export default function TypingIndicator() {
  return (
    <div className="flex justify-start">
      <Avatar role="assistant" />
      <div className="bg-[var(--color-surface-alt)] border border-[var(--color-surface)] rounded-lg p-3 max-w-[80px]">
        <div className="flex gap-1">
          <span className="w-2 h-2 rounded-full bg-[var(--color-text-secondary)] animate-dot1"></span>
          <span className="w-2 h-2 rounded-full bg-[var(--color-text-secondary)] animate-dot2"></span>
          <span className="w-2 h-2 rounded-full bg-[var(--color-text-secondary)] animate-dot3"></span>
        </div>
      </div>
    </div>
  );
}