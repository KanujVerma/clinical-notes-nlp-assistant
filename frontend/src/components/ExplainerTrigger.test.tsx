import { render, screen, fireEvent } from '@testing-library/react';
import ExplainerTrigger from './ExplainerTrigger';

describe('ExplainerTrigger — medication', () => {
  it('renders null when medication is not in dictionary', () => {
    const { container } = render(<ExplainerTrigger value="unknowndrug" kind="medication" />);
    expect(container.firstChild).toBeNull();
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
  it('renders null when abbreviation is not in dictionary', () => {
    const { container } = render(<ExplainerTrigger value="unknown" kind="abbreviation" />);
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
