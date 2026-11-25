import { UploadDropzone } from "@/components/UploadDropzone";

export default function UploadPage() {
  return (
    <div className="space-y-5 sm:space-y-6">
      <div className="space-y-1">
        <h1 className="text-xl font-bold tracking-tight text-[#0F172A] sm:text-2xl">
          Handwritten Script Upload &amp; OCR Queue
        </h1>
        <p className="text-sm leading-relaxed text-[#475569]">
          Upload handwritten student scripts to generate clean Pen-to-Print Markdown &amp; PDFs,
          or link a locked exam rubric for criterion-by-criterion evaluation.
        </p>
      </div>
      <UploadDropzone />
    </div>
  );
}
