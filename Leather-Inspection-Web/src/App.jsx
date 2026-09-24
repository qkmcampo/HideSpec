import React, { useEffect, useState } from 'react';
import { inspectionService as api, API_BASE_URL as apiBase } from './services/inspectionService';

const periods = [['today', 'Today'], ['week', '7 Days'], ['month', '30 Days'], ['all', 'All Time']];
function Card({ title, children }) {
  return <section className="card"><h2>{title}</h2>{children}</section>;
}

function Metric({ label, value, tone = '' }) {
  return <div className="metric"><span>{label}</span><strong className={tone}>{value ?? 0}</strong></div>;
}

function Monitor({ data, refresh }) {
  const [searchTerm, setSearchTerm] = useState('');
  const [resultFilter, setResultFilter] = useState('all');
  const session = data.status?.session || {};
  const stats = data.stream?.stats || {};
  const currentGrade = stats.grade || 'OFFLINE';
  const currentGradeClass = currentGrade === 'GOOD'
    ? 'good'
    : currentGrade === 'BAD'
      ? 'bad'
      : 'neutral';
  const filteredHistory = data.history.filter((item) => {
    const matchesSearch = String(item.hide_id || '').toLowerCase().includes(searchTerm.toLowerCase());
    const matchesFilter = resultFilter === 'all' || item.classification === resultFilter;
    return matchesSearch && matchesFilter;
  });

  const exportCsv = () => {
    const headers = ['Hide ID', 'Result', 'Defects', 'Defect Area (%)', 'Recorded'];
    const rows = filteredHistory.map((item) => [
      item.hide_id,
      item.classification,
      item.total_defects || 0,
      item.defect_area_percent || 0,
      item.created_at || '',
    ]);
    const csv = [headers, ...rows]
      .map((row) => row.map((value) => `"${String(value).replaceAll('"', '""')}"`).join(','))
      .join('\n');
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `hidespec-inspections-${new Date().toISOString().slice(0, 10)}.csv`;
    link.click();
    URL.revokeObjectURL(url);
  };

  return (
    <main className="page dashboard">
      <section className="monitor-summary-grid">
        <Card title="Session Summary">
          <div className="metrics session-metrics">
            <Metric label="Total inspected" value={session.total_inspected} />
            <Metric label="Passed" value={session.good_count} tone="good" />
            <Metric label="Failed" value={session.bad_count} tone="bad" />
            <Metric label="Defect rate" value={`${session.defect_rate || 0}%`} tone="accent" />
          </div>
        </Card>

        <Card title="Current Inspection Result">
          <div className={`inspection-result-card ${currentGradeClass}`}>
            <span>Current grade</span>
            <strong>{currentGrade}</strong>
            <p>{stats.reason || 'Waiting for the next inspection.'}</p>
            <div className="inspection-result-details">
              <span>Defects: <b>{stats.defect_count || 0}</b></span>
              <span>Defect area: <b>{stats.ratio || 0}%</b></span>
            </div>
          </div>
        </Card>

        <Card title="Recent Inspections">
          <div className="record-tools">
            <input
              value={searchTerm}
              onChange={(event) => setSearchTerm(event.target.value)}
              placeholder="Search Hide ID"
              aria-label="Search by Hide ID"
            />
            <select value={resultFilter} onChange={(event) => setResultFilter(event.target.value)} aria-label="Filter inspection result">
              <option value="all">All results</option>
              <option value="Good">Good only</option>
              <option value="Bad">Bad only</option>
            </select>
            <button onClick={exportCsv} disabled={!filteredHistory.length}>Export CSV</button>
          </div>
          <div className="table compact-table">
            <table>
              <thead><tr><th>Hide ID</th><th>Result</th><th>Defects</th><th>Defect Area</th><th>Recorded</th><th>Capture</th></tr></thead>
              <tbody>
                {filteredHistory.length ? filteredHistory.map((item) => (
                  <tr key={item.id || item.created_at}>
                    <td>{item.hide_id}</td>
                    <td className={item.classification === 'Good' ? 'good' : 'bad'}>{item.classification}</td>
                    <td>{item.total_defects || 0}</td>
                    <td>{item.defect_area_percent || 0}%</td>
                    <td>{item.created_at}</td>
                    <td>{item.snapshot_path ? <a href={`${apiBase}${item.snapshot_path}`} target="_blank" rel="noreferrer">View</a> : '—'}</td>
                  </tr>
                )) : <tr><td colSpan="6">No matching inspection records.</td></tr>}
              </tbody>
            </table>
          </div>
          <div className="monitor-actions">
            <span>Last record saved: {data.history[0]?.created_at || 'No records yet'}</span>
            <button onClick={refresh}>Refresh now</button>
          </div>
        </Card>

        {(data.status?.error || data.historyError) && (
          <div className="error-banner" role="alert">
            <strong>Connection error:</strong> {data.status?.error || data.historyError}
          </div>
        )}
      </section>
    </main>
  );
}

function Analytics({ data, period, setPeriod }) {
  const summary = data.summary || {};
  const defects = data.defects || [];
  const timeline = data.timeline || [];
  const quality = data.quality || {};
  const area = data.area || {};
  const maximum = Math.max(1, ...timeline.flatMap((item) => [item.good || 0, item.bad || 0]));
  const defectTypes = [
    { key: 'hole', label: 'Holes', tone: 'hole' },
    { key: 'paint_stain', label: 'Paint stains', tone: 'paint' },
    { key: 'fold', label: 'Folds', tone: 'fold' },
  ];
  const countFor = (key) => defects.find((item) => item.type === key)?.count || 0;
  const totalDefects = defectTypes.reduce((sum, item) => sum + countFor(item.key), 0);
  const maxDefectCount = Math.max(1, ...defectTypes.map((item) => countFor(item.key)));

  return (
    <main className="page analytics-page">
      <div className="analytics-header">
        <div>
          <p className="eyebrow">QUALITY CONTROL</p>
          <h1>Inspection Analytics</h1>
          <p>Track leather quality and the three detected defect categories.</p>
        </div>
        <div className="periods">
          {periods.map(([key, label]) => (
            <button className={period === key ? 'active' : ''} key={key} onClick={() => setPeriod(key)}>{label}</button>
          ))}
        </div>
      </div>

      <Card title="Inspection Overview">
        <div className="metrics">
          <Metric label="Inspected" value={summary.total_inspections} />
          <Metric label="Passed" value={summary.good_count} tone="good" />
          <Metric label="Failed" value={summary.bad_count} tone="bad" />
          <Metric label="Pass rate" value={`${summary.pass_rate || 0}%`} tone="good" />
          <Metric label="Fail rate" value={`${summary.defect_rate || 0}%`} tone="bad" />
          <Metric label="Avg. defects" value={summary.avg_defects_per_hide} tone="accent" />
        </div>
      </Card>

      <Card title="Defect Categories">
        <div className="defect-summary-grid">
          {defectTypes.map((item) => {
            const count = countFor(item.key);
            const share = totalDefects ? count / totalDefects * 100 : 0;
            return (
              <article className={`defect-summary-card ${item.tone}`} key={item.key}>
                <div className="defect-summary-top">
                  <span>{item.label}</span>
                  <strong>{count}</strong>
                </div>
                <div className="defect-bar"><i style={{ width: `${count / maxDefectCount * 100}%` }} /></div>
                <small>{share.toFixed(1)}% of detected defects</small>
              </article>
            );
          })}
        </div>
      </Card>

      <div className="analytics-columns">
        <Card title="Quality Classification">
          <div className="quality-panel">
            <strong className="quality">{summary.pass_rate || 0}%</strong>
            <span>Pass rate</span>
            <div className="progress"><i style={{ width: `${summary.pass_rate || 0}%` }} /></div>
            <div className="quality-breakdown">
              <span className="good">Good: {quality.good || summary.good_count || 0}</span>
              <span className="bad">Bad: {quality.bad || summary.bad_count || 0}</span>
            </div>
          </div>
        </Card>
        <Card title="Defect Area Threshold">
          <div className="metrics threshold-metrics">
            <Metric label="Threshold" value={`${quality.threshold_percent || 20}%`} tone="accent" />
            <Metric label="Average area" value={`${area.avg_percent || 0}%`} tone="accent" />
            <Metric label="Above threshold" value={quality.bad || 0} tone="bad" />
          </div>
        </Card>
      </div>

      {timeline.length > 0 && (
        <Card title="Inspection Timeline">
          <div className="chart">
            {timeline.map((item, index) => (
              <div className="chart-item" key={`${item.time_label}-${index}`}>
                <div>
                  <i className="good-bar" style={{ height: `${(item.good || 0) / maximum * 100}%` }} />
                  <i className="bad-bar" style={{ height: `${(item.bad || 0) / maximum * 100}%` }} />
                </div>
                <small>{item.time_label}</small>
              </div>
            ))}
          </div>
        </Card>
      )}
    </main>
  );
}

export default function App() {
  const [tab, setTab] = useState('monitor');
  const [period, setPeriod] = useState('all');
  const [monitor, setMonitor] = useState({ status: {}, history: [], historyError: '' });
  const [analytics, setAnalytics] = useState({ loading: false, summary: {}, defects: [], timeline: [], quality: {}, area: {} });

  const refreshAnalytics = async () => {
    setAnalytics((current) => ({ ...current, loading: true }));
    try {
      const [summary, defects, timeline, quality, area] = await Promise.all([
        api.analytics(period),
        api.defects(period),
        api.timeline(period),
        api.quality(period),
        api.defectArea(period),
      ]);
      setAnalytics({
        loading: false,
        summary,
        defects: defects.defects || [],
        timeline: timeline.timeline || [],
        quality,
        area,
      });
    } catch {
      setAnalytics({ loading: false, summary: {}, defects: [], timeline: [], quality: {}, area: {} });
    }
  };

  const refreshMonitor = async () => {
    const [status, history, stream] = await Promise.all([
      api.status(),
      api.history(),
      api.stream(),
    ]);
    setMonitor((current) => ({
      ...current,
      status,
      stream,
      history: history.inspections || [],
      historyError: history.error || '',
      reset: async () => {
        if (window.confirm('Reset all inspection history?')) {
          await api.reset();
          refreshMonitor();
        }
      },
    }));
  };

  useEffect(() => {
    refreshMonitor();
    const timer = setInterval(refreshMonitor, 2000);
    return () => {
      clearInterval(timer);
    };
  }, []);

  useEffect(() => {
    if (tab === 'analytics') {
      refreshAnalytics();
      const timer = setInterval(refreshAnalytics, 2000);
      return () => clearInterval(timer);
    }
  }, [tab, period]);

  const page = tab === 'monitor'
    ? <Monitor data={monitor} refresh={refreshMonitor} />
    : <Analytics data={analytics} period={period} setPeriod={setPeriod} />;

  return (
    <div className="app">
      <header>
        <b>HIDESPEC</b>
        <nav>{[['monitor', 'Monitor'], ['analytics', 'Analytics']].map(([key, label]) => <button key={key} className={tab === key ? 'selected' : ''} onClick={() => setTab(key)}>{label}</button>)}</nav>
      </header>
      {page}
    </div>
  );
}


