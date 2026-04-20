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

describe('ExplainerPopover — AI actions', () => {
  const mockSingleAbbrev: AbbreviationExplanation[] = [
    { abbreviation: 'BID', expansion: 'Twice daily', category: 'frequency' },
  ];

  it('medication hit + AI available → renders "Explain in more detail →" button, not "Generate AI explanation"', () => {
    const onRequestAi = vi.fn();
    render(
      <ExplainerPopover
        top={100}
        left={100}
        medication={mockMed}
        hasDictionaryEntry={true}
        kind="medication"
        aiAvailable={true}
        onRequestAi={onRequestAi}
        onClose={() => {}}
      />
    );
    expect(screen.getByText('Explain in more detail →')).toBeInTheDocument();
    expect(screen.queryByText('Generate AI explanation')).not.toBeInTheDocument();
  });

  it('medication miss + AI available → renders "No built-in explanation available" AND "Generate AI explanation"', () => {
    const onRequestAi = vi.fn();
    render(
      <ExplainerPopover
        top={100}
        left={100}
        medication={undefined}
        abbreviations={[]}
        hasDictionaryEntry={false}
        kind="medication"
        aiAvailable={true}
        onRequestAi={onRequestAi}
        onClose={() => {}}
      />
    );
    expect(screen.getByText('No built-in explanation available for this term.')).toBeInTheDocument();
    expect(screen.getByText('Generate AI explanation')).toBeInTheDocument();
  });

  it('abbreviation hit + AI available → NO AI button rendered', () => {
    const onRequestAi = vi.fn();
    render(
      <ExplainerPopover
        top={100}
        left={100}
        abbreviations={mockSingleAbbrev}
        hasDictionaryEntry={true}
        kind="abbreviation"
        aiAvailable={true}
        onRequestAi={onRequestAi}
        onClose={() => {}}
      />
    );
    expect(screen.queryByText('Explain in more detail →')).not.toBeInTheDocument();
    expect(screen.queryByText('Generate AI explanation')).not.toBeInTheDocument();
  });

  it('abbreviation miss + AI available → renders "No built-in explanation available" AND "Generate AI explanation"', () => {
    const onRequestAi = vi.fn();
    render(
      <ExplainerPopover
        top={100}
        left={100}
        abbreviations={[]}
        hasDictionaryEntry={false}
        kind="abbreviation"
        aiAvailable={true}
        onRequestAi={onRequestAi}
        onClose={() => {}}
      />
    );
    expect(screen.getByText('No built-in explanation available for this term.')).toBeInTheDocument();
    expect(screen.getByText('Generate AI explanation')).toBeInTheDocument();
  });

  it('AI unavailable → no AI buttons rendered (medication miss case)', () => {
    const onRequestAi = vi.fn();
    render(
      <ExplainerPopover
        top={100}
        left={100}
        medication={undefined}
        abbreviations={[]}
        hasDictionaryEntry={false}
        kind="medication"
        aiAvailable={false}
        onRequestAi={onRequestAi}
        onClose={() => {}}
      />
    );
    expect(screen.queryByText('Generate AI explanation')).not.toBeInTheDocument();
    expect(screen.queryByText('Explain in more detail →')).not.toBeInTheDocument();
  });

  it('clicking "Generate AI explanation" on miss calls onRequestAi with (kind, value) and calls onClose', () => {
    const onRequestAi = vi.fn();
    const onClose = vi.fn();
    render(
      <ExplainerPopover
        top={100}
        left={100}
        medication={undefined}
        abbreviations={mockSingleAbbrev}
        hasDictionaryEntry={false}
        kind="abbreviation"
        aiAvailable={true}
        onRequestAi={onRequestAi}
        onClose={onClose}
      />
    );
    fireEvent.click(screen.getByText('Generate AI explanation'));
    expect(onRequestAi).toHaveBeenCalledWith('abbreviation', 'BID', undefined);
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('clicking "Explain in more detail" on medication hit calls onRequestAi and calls onClose', () => {
    const onRequestAi = vi.fn();
    const onClose = vi.fn();
    render(
      <ExplainerPopover
        top={100}
        left={100}
        medication={mockMed}
        hasDictionaryEntry={true}
        kind="medication"
        aiAvailable={true}
        onRequestAi={onRequestAi}
        onClose={onClose}
      />
    );
    fireEvent.click(screen.getByText('Explain in more detail →'));
    expect(onRequestAi).toHaveBeenCalledWith('medication', 'Metformin', undefined);
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
