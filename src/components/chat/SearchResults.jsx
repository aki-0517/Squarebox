import React from 'react';

export default function SearchResults({ results }) {
  return (
    <div className="mt-4 p-4 bg-white border border-[var(--color-surface)] rounded-lg shadow-md">
      <h2 className="text-lg font-bold text-[var(--color-text-primary)]">Search Results</h2>
      <ul className="mt-2 space-y-2">
        {results.map((result, index) => (
          <li key={index} className="p-2 border-b border-[var(--color-surface-alt)]">
            <a href={result.link} className="text-[var(--color-primary)] hover:underline">
              {result.title}
            </a>
            <p className="text-[var(--color-text-secondary)]">{result.description}</p>
          </li>
        ))}
      </ul>
    </div>
  );
} 