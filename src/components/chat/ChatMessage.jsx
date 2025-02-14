import PropTypes from 'prop-types';
import Avatar from './Avatar';

export default function ChatMessage({ message }) {
  const isUser = message.role === 'user';

  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}>
      {!isUser && <Avatar role="assistant" />}
      <div className={`max-w-[80%] p-3 rounded-lg bg-white border border-[var(--color-surface)] shadow-md`}>
        <p className={`text-[var(--color-text-primary)] ${
          !isUser && 'opacity-90'
        }`}>
          {message.content}
        </p>
      </div>
    </div>
  );
}

ChatMessage.propTypes = {
  message: PropTypes.shape({
    content: PropTypes.string.isRequired,
    role: PropTypes.oneOf(['user', 'assistant']).isRequired,
    id: PropTypes.number.isRequired
  }).isRequired
};