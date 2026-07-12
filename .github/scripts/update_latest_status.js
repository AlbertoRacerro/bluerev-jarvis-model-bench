'use strict';

module.exports = async function updateLatestStatus({
  github,
  context,
  issueNumber,
  section,
  title,
  payload,
}) {
  if (!Number.isInteger(issueNumber) || issueNumber <= 0) {
    throw new Error(`invalid issue number: ${issueNumber}`);
  }
  if (!/^[a-z0-9-]+$/.test(section)) {
    throw new Error(`invalid status section: ${section}`);
  }

  const start = `<!-- ${section}:start -->`;
  const end = `<!-- ${section}:end -->`;
  const replacement = [
    start,
    `## ${title}`,
    '',
    `Updated: ${new Date().toISOString()}`,
    '',
    '```json',
    JSON.stringify(payload, null, 2),
    '```',
    end,
  ].join('\n');

  const { data: issue } = await github.rest.issues.get({
    owner: context.repo.owner,
    repo: context.repo.repo,
    issue_number: issueNumber,
  });
  const currentBody = issue.body || '';
  const startIndex = currentBody.indexOf(start);
  const endIndex = currentBody.indexOf(end, startIndex + start.length);
  if (startIndex < 0 || endIndex < 0) {
    throw new Error(`status section markers not found for ${section}`);
  }
  const updatedBody =
    currentBody.slice(0, startIndex) +
    replacement +
    currentBody.slice(endIndex + end.length);

  await github.rest.issues.update({
    owner: context.repo.owner,
    repo: context.repo.repo,
    issue_number: issueNumber,
    body: updatedBody,
  });
};
