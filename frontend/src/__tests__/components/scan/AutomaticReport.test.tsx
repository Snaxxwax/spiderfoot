import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
vi.mock('../../../lib/api', async () => {
  const actual = await vi.importActual<Record<string, unknown>>('../../../lib/api');
  return { ...actual,
    default: { get: vi.fn() },
    scanApi: { summary: vi.fn().mockResolvedValue({ details: [] }), correlations: vi.fn().mockResolvedValue({ correlations: [] }), events: vi.fn().mockResolvedValue({ events: [] }) },
  };
});
import api from '../../../lib/api';
import ReportTab from '../../../components/scan/ReportTab';
function wrapper({children}: {children: React.ReactNode}) {
  return <QueryClientProvider client={new QueryClient({defaultOptions:{queries:{retry:false}}})}>{children}</QueryClientProvider>;
}
describe('automatic report delivery', () => {
  beforeEach(() => { localStorage.clear(); vi.clearAllMocks(); });
  it('loads a completed background report without a Generate click', async () => {
    vi.mocked(api.get).mockResolvedValue({ data: { state: 'complete', report: '# Automatic evidence report' } });
    render(<ReportTab scanId="fixture-scan" />, { wrapper });
    expect(await screen.findByText('Automatic evidence report')).toBeTruthy();
  });
  it('keeps locally saved user edits', async () => {
    localStorage.setItem('sf_report_fixture-scan', '# User edited report');
    vi.mocked(api.get).mockResolvedValue({ data: { state: 'complete', report: '# Automatic evidence report' } });
    render(<ReportTab scanId="fixture-scan" />, { wrapper });
    expect(await screen.findByText('User edited report')).toBeTruthy();
    expect(screen.queryByText('Automatic evidence report')).toBeNull();
  });
  it('shows setup status without pretending a report exists', async () => {
    vi.mocked(api.get).mockResolvedValue({ data: { state: 'waiting_configuration' } });
    render(<ReportTab scanId="fixture-scan" />, { wrapper });
    expect(await screen.findByText('Automatic analysis is awaiting administrator setup.')).toBeTruthy();
  });
});
