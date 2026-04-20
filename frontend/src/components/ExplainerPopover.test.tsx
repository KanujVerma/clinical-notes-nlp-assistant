import { render, screen, fireEvent } from '@testing-library/react';
import ExplainerPopover from './ExplainerPopover';
import type { MedicationExplanation } from '../data/medicationExplanations';
import type { AbbreviationExplanation } from '../data/clinicalAbbreviations';

const mockMed: MedicationExplanation = {
  name: 'Metformin',
  description: 'Lowers blood glucose by reducing liver glucose output',
  commonUse: 'Type 2 diabetes management',
  drugClass: 'Biguanide',
};

const mockAbbrevs: AbbreviationExplanation[] = [
  { abbreviation: 'BID', expansion: 'Twice daily', category: 'frequency' },
  { abbreviation: 'PRN', expansion: 'As needed', category: 'qualifier' },
];

describe('ExplainerPopover — medication', () => {
  it('renders medication name', () => {
    render(<ExplainerPopover top={100} left={100} medication={mockMed} onClose={() => {}} />);
    expect(screen.getByText('Metformin')).toBeInTheDocument();
  });

  it('renders description, commonUse, drugClass', () => {
    render(<ExplainerPopover top={100} left={100} medication={mockMed} onClose={() => {}} />);
    expect(screen.getByText('Lowers blood glucose by reducing liver glucose output')).toBeInTheDocument();
    expect(screen.getByText('Type 2 diabetes management')).toBeInTheDocument();
    expect(screen.getByText('Biguanide')).toBeInTheDocument();
  });

  it('renders the disclaimer line', () => {
    render(<ExplainerPopover top={100} left={100} medication={mockMed} onClose={() => {}} />);
    expect(screen.getByText('Informational only — not medical advice.')).toBeInTheDocument();
  });

  it('calls onClose when Escape is pressed', () => {
    const onClose = vi.fn();
    render(<ExplainerPopover top={100} left={100} medication={mockMed} onClose={onClose} />);
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('calls onClose when close button is clicked', () => {
    const onClose = vi.fn();
    render(<ExplainerPopover top={100} left={100} medication={mockMed} onClose={onClose} />);
    fireEvent.click(screen.getByRole('button', { name: /close/i }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});

describe('ExplainerPopover — abbreviations', () => {
  it('renders each abbreviation and its expansion', () => {
    render(<ExplainerPopover top={100} left={100} abbreviations={mockAbbrevs} onClose={() => {}} />);
    expect(screen.getByText('BID')).toBeInTheDocument();
    expect(screen.getByText('Twice daily')).toBeInTheDocument();
    expect(screen.getByText('PRN')).toBeInTheDocument();
    expect(screen.getByText('As needed')).toBeInTheDocument();
  });

  it('renders the disclaimer line', () => {
    render(<ExplainerPopover top={100} left={100} abbreviations={mockAbbrevs} onClose={() => {}} />);
    expect(screen.getByText('Informational only — not medical advice.')).toBeInTheDocument();
  });
});
