import React from 'react';

const TagButton = ({ tag, onClick }) => {
  return (
    <button
      onClick={() => onClick(tag)}
      className="px-2 py-1 bg-blue-100 text-blue-700 rounded-full text-sm hover:bg-blue-200 transition duration-200"
    >
      {tag}
    </button>
  );
};

export default TagButton;
