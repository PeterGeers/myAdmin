import { extendTheme } from '@chakra-ui/react';

const theme = extendTheme({
    styles: {
        global: {
            body: {
                bg: '#0f0f0f',
                color: '#f2f2f2',
            },
            'select': {
                bg: '#ff6600 !important',
                color: 'white !important',
            },
            'select option': {
                bg: '#ff6600 !important',
                color: 'white !important',
            },
            'select option:hover': {
                bg: '#e55a00 !important',
                color: 'white !important',
            },
            'select option:checked': {
                bg: '#e55a00 !important',
                color: 'white !important',
            },
        },
    },
    colors: {
        brand: {
            orange: '#ff6600',
            gray: '#1a1a1a',
        },
    },
    components: {
        Select: {
            baseStyle: {
                field: {
                    bg: 'brand.orange',
                    color: 'white',
                    fontSize: 'sm',
                    height: '32px',
                    _hover: {
                        bg: '#e55a00',
                    },
                },
            },
            variants: {
                outline: {
                    field: {
                        bg: 'brand.orange',
                        color: 'white',
                        borderColor: 'brand.orange',
                        fontSize: 'sm',
                        height: '32px',
                        _hover: {
                            bg: '#e55a00',
                            borderColor: '#e55a00',
                        },
                    },
                },
            },
        },
        Menu: {
            baseStyle: {
                list: {
                    bg: 'brand.orange',
                    borderColor: 'brand.orange',
                },
                item: {
                    bg: 'brand.orange',
                    color: 'white',
                    _hover: {
                        bg: '#e55a00',
                        color: 'white',
                    },
                    _focus: {
                        bg: '#e55a00',
                        color: 'white',
                    },
                },
            },
        },
        Input: {
            baseStyle: {
                field: {
                    color: 'black',
                    bg: 'white',
                    _placeholder: {
                        color: 'gray.500',
                    },
                },
            },
            variants: {
                outline: {
                    field: {
                        color: 'black',
                        bg: 'white',
                        borderColor: 'gray.300',
                        _placeholder: {
                            color: 'gray.500',
                        },
                    },
                },
            },
        },
    },
});

export default theme;