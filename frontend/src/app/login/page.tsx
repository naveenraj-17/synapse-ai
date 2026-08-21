import { LoginForm } from './LoginForm';

/**
 * `redirect` is read on the SERVER and passed down.
 *
 * This page used to call useSearchParams() inside a <Suspense> boundary, which
 * opts that whole subtree out of prerendering — so the initial HTML contained
 * no <form> and no <input> at all, and the sign-in box only appeared once JS
 * had loaded and hydrated.
 */
export default async function LoginPage(props: {
    searchParams: Promise<{ [key: string]: string | string[] | undefined }>;
}) {
    const searchParams = await props.searchParams;
    const requested = typeof searchParams.redirect === 'string' ? searchParams.redirect : '/';

    // Only same-origin paths. `//evil.example` is a protocol-relative URL and
    // would otherwise turn this into an open redirect.
    const redirectTo = requested.startsWith('/') && !requested.startsWith('//') ? requested : '/';

    return <LoginForm redirectTo={redirectTo} />;
}
