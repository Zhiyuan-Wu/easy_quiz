\NeedsTeXFormat{LaTeX2e}
\ProvidesClass{exam-zh}[2025/11/03 Minimal exam class]

\LoadClass{article}

\RequirePackage{ctex}
\RequirePackage{geometry}
\RequirePackage{amsmath, amssymb}
\RequirePackage{graphicx}
\RequirePackage{enumitem}
\RequirePackage{siunitx}
\RequirePackage{xcolor}

\geometry{a4paper, left=25mm, right=25mm, top=25mm, bottom=25mm}

\setlength{\parindent}{2em}
\setlength{\parskip}{0.5em}

\makeatletter
\def\exam@subject{}
\def\exam@info{}
\def\exam@secret{false}

\newcommand{\subject}[1]{\def\exam@subject{#1}}
\newcommand{\information}[1]{\def\exam@info{#1}}
\newcommand{\secret}{\def\exam@secret{true}}
\newcommand{\examsetup}[1]{}

\renewcommand{\maketitle}{%
  \begin{center}
    {\bfseries\zihao{2} \@title\par}
    \vspace{0.6em}
    {\zihao{-2} \exam@subject\par}
    \vspace{1.2em}
  \end{center}%
  \ifx\exam@info\@empty\else
    \noindent\exam@info\par
  \fi
  \vspace{1.2em}
}
\makeatother

\newenvironment{notice}{\begin{enumerate}[label=\arabic*.\ , leftmargin=2.2em, itemsep=0.6em]}{\end{enumerate}}

\newenvironment{question}{\par\medskip\noindent\ignorespaces}{\par\medskip}
\newenvironment{solution}{\par\medskip\noindent\textbf{参考解答：}\par\smallskip\ignorespaces}{\par\medskip}
\newenvironment{choices}{\begin{enumerate}[label=\Alph*.\ , leftmargin=2.5em, itemsep=0.4em]}{\end{enumerate}}

\newcommand{\textfigure}[2]{%
  \begin{minipage}[t]{0.52\linewidth}#1\end{minipage}\hfill
  \begin{minipage}[t]{0.44\linewidth}\centering #2\end{minipage}\par
}
