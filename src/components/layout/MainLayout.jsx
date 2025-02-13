import Sidebar from './Sidebar';

export default function MainLayout({ children }) {
  return (
    <div className="flex h-full w-full bg-[var(--color-background)]">
      <Sidebar />
      <main className="flex-1 overflow-hidden">
        {children}
      </main>
    </div>
  );
}