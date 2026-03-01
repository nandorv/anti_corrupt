import './TitleBar.css';

export default function TitleBar() {
  return (
    <header className="title-bar">
      <span className="logo">🔍</span>
      <h1>Anti-Corrupt</h1>
      <span className="subtitle">Data Pipeline Architecture</span>
      <div className="stats">
        <span>Politicians <span className="stat-value">13,724</span></span>
        <span>Expenses <span className="stat-value">171,321</span></span>
        <span>Companies <span className="stat-value">16,502</span></span>
        <span>Votes <span className="stat-value">4,996</span></span>
        <span>Elections <span className="stat-value">12,820</span></span>
        <span>Cabinet <span className="stat-value">22,338</span></span>
        <span>Tables <span className="stat-value">9</span></span>
        <span>DBs <span className="stat-value">5</span></span>
      </div>
    </header>
  );
}
