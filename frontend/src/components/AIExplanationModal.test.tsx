import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import AIExplanationModal from './AIExplanationModal';
import type { AiExplanation } from '../lib/aiExplain';

const baseProps = {
  term: 'Metformin',
  loading: false,
  onClose: vi.fn(),
};

const explanation: AiExplanation = {
  whatItIs: 'A biguanide antidiabetic drug',
  commonUse: 'Type 2 diabetes management',
  plainLanguage: 'Lowers blood sugar by reducing liver glucose production',
};

const explanationWithUncertainty: AiExplanation = {
  ...explanation,
  uncertainty: 'May interact with contrast dye',
};

describe('AIExplanationModal', () => {
  it('shows loading text when loading=true', () => {
    render(<AIExplanationModal {...baseProps} loading={true} />);
    expect(screen.getByText('Generating explanation…')).toBeInTheDocument();
  });

  it('shows explanation rows when loaded', () => {
    render(<AIExplanationModal {...baseProps} explanation={explanation} />);
    expect(screen.getByText('A biguanide antidiabetic drug')).toBeInTheDocument();
    expect(screen.getByText('Type 2 diabetes management')).toBeInTheDocument();
    expect(screen.getByText('Lowers blood sugar by reducing liver glucose production')).toBeInTheDocument();
  });

  it('shows optional uncertainty row when present', () => {
    render(<AIExplanationModal {...baseProps} explanation={explanationWithUncertainty} />);
    expect(screen.getByText('May interact with contrast dye')).toBeInTheDocument();
    expect(screen.getByText('Note')).toBeInTheDocument();
  });

  it('does not show uncertainty row when absent', () => {
    render(<AIExplanationModal {...baseProps} explanation={explanation} />);
    expect(screen.queryByText('Note')).not.toBeInTheDocument();
  });

  it('shows error message when error is set', () => {
    render(<AIExplanationModal {...baseProps} error="Something went wrong" />);
    expect(screen.getByText('Something went wrong')).toBeInTheDocument();
  });

  it('renders disclaimer in all states', () => {
    const { rerender } = render(<AIExplanationModal {...baseProps} loading={true} />);
    expect(screen.getByText(/AI-generated explanation for informational review only/)).toBeInTheDocument();

    rerender(<AIExplanationModal {...baseProps} explanation={explanation} />);
    expect(screen.getByText(/AI-generated explanation for informational review only/)).toBeInTheDocument();

    rerender(<AIExplanationModal {...baseProps} error="err" />);
    expect(screen.getByText(/AI-generated explanation for informational review only/)).toBeInTheDocument();
  });

  it('calls onClose when Escape is pressed', () => {
    const onClose = vi.fn();
    render(<AIExplanationModal {...baseProps} onClose={onClose} explanation={explanation} />);
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('calls onClose when backdrop is clicked', () => {
    const onClose = vi.fn();
    const { container } = render(
      <AIExplanationModal {...baseProps} onClose={onClose} explanation={explanation} />
    );
    // The backdrop is the outermost div (fixed inset-0)
    const backdrop = container.firstChild as HTMLElement;
    fireEvent.mouseDown(backdrop);
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('does not call onClose when card is clicked', () => {
    const onClose = vi.fn();
    render(<AIExplanationModal {...baseProps} onClose={onClose} explanation={explanation} />);
    // Click on the term text inside the card
    fireEvent.mouseDown(screen.getByText('Metformin'));
    expect(onClose).not.toHaveBeenCalled();
  });
});
