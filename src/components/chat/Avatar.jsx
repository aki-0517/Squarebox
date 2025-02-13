export default function Avatar({ role }) {
  if (role === 'user') return null;

  return (
    <div className="w-8 h-8 rounded-full bg-[var(--color-primary)] flex items-center justify-center mr-2">
      <span className="text-sm font-medium text-white">AI</span>
    </div>
  );
}