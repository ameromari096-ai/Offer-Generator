// Builds the offer-email subject/body and the fixed onboarding-documents
// attachment list, mirroring the recruiter's real "PureHealth - Offer
// Letter" email (name/role are the only things that change email to
// email; the checklist, forms link, and signature are the same every
// time, so they're editable defaults rather than hard-coded).
(function (global) {
  const SUBJECT = 'PureHealth - Offer Letter';

  // Filenames must match assets/offer-attachments/ exactly.
  const FIXED_ATTACHMENTS = [
    'Acceptable Use - Acknowledgement Form v3.0.docx',
    'Visa-Photo.pdf',
    'Generic DataFlow LOA.pdf',
    'Candidate Disclosure Form - Jan 2024.docx',
    'Employee Record Form.xlsx'
  ];
  const FIXED_ATTACHMENTS_DIR = 'assets/offer-attachments/';

  const DEFAULT_FORMS_LINK = 'https://forms.office.com/r/7BPEMqfh7y';
  const DEFAULT_SENDER = {
    name: 'Amer Omari',
    title: 'Specialist - Talent Acquisition',
    phoneOffice: '+971 4 447 3338',
    phoneMobile: '+971 50 833 8074'
  };

  function escapeHtml(s) {
    return String(s || '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function firstName(fullName) {
    return (fullName || '').trim().split(/\s+/)[0] || '';
  }

  function buildSubject() {
    return SUBJECT;
  }

  /**
   * The employment contract attachment is renamed to match the recruiter's
   * existing naming convention ("<Candidate Name> - PureHealth -
   * Employment Contract.<ext>") instead of keeping whatever filename the
   * uploaded file happened to have.
   */
  function contractAttachmentFilename(candidateName, originalFilename) {
    const ext = (originalFilename.split('.').pop() || 'pdf').toLowerCase();
    return `${candidateName} - PureHealth - Employment Contract.${ext}`;
  }

  /**
   * state: { candidateName, jobTitle, formsLink, sender: { name, title,
   *          phoneOffice, phoneMobile } }
   */
  function buildEmailHtml(state) {
    const sender = state.sender || DEFAULT_SENDER;
    const formsLink = state.formsLink || DEFAULT_FORMS_LINK;
    return `<div style="font-family: Segoe UI, Arial, sans-serif; font-size: 14px; color: #222222; line-height: 1.6;">
  <p>Dear ${escapeHtml(firstName(state.candidateName))},</p>
  <p>Greetings from Purehealth.</p>
  <p>We are pleased to share with you our offer for the role of &ldquo;${escapeHtml(state.jobTitle)}&rdquo;</p>
  <p>Your detailed Employment Offer is attached for your review. The next steps are as follows:</p>
  <ol>
    <li>You must provide your acceptance on the Offer Letter (Affix your signature on all the pages of the offer letter) as per the formalities mentioned in the same.</li>
    <li>We will be in contact with you regarding your employment visa formalities following your offer acceptance.</li>
    <li>Pure Health reserves the right to withdraw the offer if the joining date is deferred and/or not mutually agreed.</li>
  </ol>
  <p>Based on your acceptance, you are kindly requested to share with us the required documents to proceed with your joining formalities. These documents are:</p>
  <ol>
    <li>Passport copy (with the validity of more than 180 days)</li>
    <li>Salary payslip or salary certificate (from previous employer) &ndash; Mandatory</li>
    <li>Attested education certificates (It must be attested from the authorities in your home country in addition to the UAE embassy in your home country. Once in UAE, it has to be attested as well from the UAE Ministry of foreigner)</li>
    <li>Work experience certificates from previous employer</li>
    <li>Passport photograph (white background)</li>
    <li>Employee Record Form &amp; Other forms (attached)</li>
    <li>Emirates ID &amp; Residency Visa (if in UAE)</li>
    <li>Please login to this link and fill out the form: <a href="${escapeHtml(formsLink)}" target="_blank" rel="noopener">${escapeHtml(formsLink)}</a></li>
  </ol>
  <p>You are requested to kindly revert and confirm your acceptance, also please let us know your tentative date of joining.</p>
  <p>For further queries please feel free to contact us.</p>
  <p>Best Regards,</p>
  <p>
    ${escapeHtml(sender.name)}<br>
    ${escapeHtml(sender.title)}<br>
    T ${escapeHtml(sender.phoneOffice)}<br>
    M ${escapeHtml(sender.phoneMobile)}<br>
    <a href="https://purehealth.ae/" target="_blank" rel="noopener">purehealth.ae</a>
  </p>
  <p style="font-size: 12px; color: #666666;">Save Trees. Do Not Print</p>
  <p style="font-size: 11px; color: #888888;">This is an e-mail from Pure Health Medical Supplies LLC. Its contents are confidential to the intended recipient. If you are not the intended recipient, be advised that you have received this e-mail in error and that any use, dissemination, forwarding, printing or copying of this e-mail is strictly prohibited. It may not be disclosed to or used by anyone other than its intended recipient, nor may it be copied in any way. If received in error, please email a reply to the sender and then delete it from your system.</p>
</div>`;
  }

  const api = {
    SUBJECT,
    FIXED_ATTACHMENTS,
    FIXED_ATTACHMENTS_DIR,
    DEFAULT_FORMS_LINK,
    DEFAULT_SENDER,
    escapeHtml,
    firstName,
    buildSubject,
    contractAttachmentFilename,
    buildEmailHtml
  };

  const root = global.PH || (global.PH = {});
  root.offerTemplates = api;
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = api;
  }
})(typeof window !== 'undefined' ? window : globalThis);
