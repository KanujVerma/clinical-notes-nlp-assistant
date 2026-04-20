import { render, screen, fireEvent } from '@testing-library/react';
import ExplainerTrigger from './ExplainerTrigger';

describe('ExplainerTrigger — medication', () => {
  it('renders info button when medication is NOT in dictionary (hasDictionaryEntry=false)', () => {
    render(<ExplainerTrigger value="unknowndrug" kind="medication" />);
    expect(screen.getByRole('button', { name: /show explanation/i })).toBeInTheDocument();
  });

  it('renders info button when medication is in dictionary', () => {
    render(<ExplainerTrigger value="metformin" kind="medication" />);
    expect(screen.getByRole('button', { name: /show explanation/i })).toBeInTheDocument();
  });

  it('shows popover with medication name on click', () => {
    render(<ExplainerTrigger value="metformin" kind="medication" />);
    fireEvent.click(screen.getByRole('button', { name: /show explanation/i }));
    expect(screen.getByText('Metformin')).toBeInTheDocument();
  });

  it('hides popover on second click (toggle)', () => {
    render(<ExplainerTrigger value="metformin" kind="medication" />);
    const btn = screen.getByRole('button', { name: /show explanation/i });
    fireEvent.click(btn);
    expect(screen.getByText('Metformin')).toBeInTheDocument();
    fireEvent.click(btn);
    expect(screen.queryByText('Metformin')).not.toBeInTheDocument();
  });

  it('calls e.stopPropagation on click', () => {
    const parentHandler = vi.fn();
    render(
      <div onClick={parentHandler}>
        <ExplainerTrigger value="metformin" kind="medication" />
      </div>
    );
    fireEvent.click(screen.getByRole('button', { name: /show explanation/i }));
    expect(parentHandler).not.toHaveBeenCalled();
  });
});

describe('ExplainerTrigger — abbreviation', () => {
  it('renders info button when abbreviation is unknown but not denylisted (hasDictionaryEntry=false)', () => {
    render(<ExplainerTrigger value="with meals" kind="abbreviation" />);
    expect(screen.getByRole('button', { name: /show explanation/i })).toBeInTheDocument();
  });

  it('renders null when abbreviation is unknown and denylisted', () => {
    const { container } = render(<ExplainerTrigger value="twice daily" kind="abbreviation" />);
    expect(container.firstChild).toBeNull();
  });

  it('renders info button for a known abbreviation (BID)', () => {
    render(<ExplainerTrigger value="BID" kind="abbreviation" />);
    expect(screen.getByRole('button', { name: /show explanation/i })).toBeInTheDocument();
  });

  it('shows popover with abbreviation expansion on click', () => {
    render(<ExplainerTrigger value="BID" kind="abbreviation" />);
    fireEvent.click(screen.getByRole('button', { name: /show explanation/i }));
    expect(screen.getByText('Twice daily')).toBeInTheDocument();
  });
});

describe('ExplainerTrigger — AI forwarding', () => {
  it('calls onRequestAi with kind and value when AI action is clicked', async () => {
    const onRequestAi = vi.fn();
    render(
      <ExplainerTrigger
        value="metformin"
        kind="medication"
        aiAvailable={true}
        onRequestAi={onRequestAi}
      />
    );
    const btn = screen.getByLabelText('Show explanation');
    fireEvent.click(btn);
    // Click the "Explain in more detail" link
    const aiBtn = await screen.findByText(/Explain in more detail/i);
    fireEvent.click(aiBtn);
    expect(onRequestAi).toHaveBeenCalledWith('medication', 'Metformin', undefined);
  });
});
